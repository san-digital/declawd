#!/usr/bin/env python3
"""Generate token-only teaching traces with pinned public model revisions.

The input and output are token IDs. The runner never writes decoded model text.
Gemma requires the model licence to have been accepted for the caller's
Hugging Face account.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
from typing import Any

from synthid_reference import (
    CONTEXT_HISTORY_SIZE,
    KEYS,
    NGRAM_LEN,
    PROFILE_ID,
    PROFILE_SHA256,
    SAMPLING_TABLE_SEED,
    TABLE_SIZE,
    expected_from_report,
    load_sampling_table,
    parse_strict_json_bytes,
    score_trace,
)


ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "gpt2": {
        "repository": "openai-community/gpt2",
        "revision": "607a30d783dfa663caf39e06633721c8d4cfcd7e",
        "class": "GPT2LMHeadModel",
    },
    "gemma-2b-it": {
        "repository": "google/gemma-2b-it",
        "revision": "96988410cbdaeb8d5093d1ebdc5a8fb563e02bad",
        "class": "GemmaForCausalLM",
    },
}
TORCH_VERSION = "2.13.0"
TRANSFORMERS_VERSION = "5.15.0"
SAFETENSORS_VERSION = "0.8.0"


def verify_runner_install(torch: Any) -> None:
    installed = {
        "torch": torch.__version__.split("+", 1)[0],
        "transformers": importlib.metadata.version("transformers"),
        "safetensors": importlib.metadata.version("safetensors"),
    }
    expected = {
        "torch": TORCH_VERSION,
        "transformers": TRANSFORMERS_VERSION,
        "safetensors": SAFETENSORS_VERSION,
    }
    if installed != expected:
        raise ValueError(f"expected runner versions {expected}, found {installed}")


def read_table(torch: Any, device: Any) -> Any:
    packed = load_sampling_table()
    bits = [
        (packed[index // 8] >> (index % 8)) & 1
        for index in range(65_536)
    ]
    return torch.tensor(bits, dtype=torch.int64, device=device)


def validate_input(
    input_document: Any, requested_model: str, model_spec: dict[str, str]
) -> list[int]:
    required_input_fields = {
        "schema", "model", "repository", "revision", "prompt_token_ids"
    }
    if not isinstance(input_document, dict) or set(input_document) != required_input_fields:
        raise ValueError("input must contain exactly the v1 model-input fields")
    if input_document["schema"] != "declawd.synthid-model-input/v1":
        raise ValueError("input schema must be declawd.synthid-model-input/v1")
    expected_model = input_document["model"]
    if expected_model != requested_model:
        raise ValueError(
            f"input model {expected_model!r} does not match {requested_model!r}"
        )
    if input_document["repository"] != model_spec["repository"]:
        raise ValueError("input repository does not match the pinned model repository")
    if input_document["revision"] != model_spec["revision"]:
        raise ValueError("input revision does not match the pinned model revision")
    token_ids = input_document["prompt_token_ids"]
    if (
        not isinstance(token_ids, list)
        or not token_ids
        or len(token_ids) > 100_000
        or any(type(token) is not int or token < 0 for token in token_ids)
    ):
        raise ValueError("input requires a non-empty prompt_token_ids array")
    return token_ids


def validate_vocabulary(token_ids: list[int], vocabulary_size: int) -> None:
    if any(token >= vocabulary_size for token in token_ids):
        raise ValueError(
            f"prompt token IDs must be below the loaded vocabulary size {vocabulary_size}"
        )


def load_input(path: Path, requested_model: str, model_spec: dict[str, str]) -> list[int]:
    return validate_input(parse_strict_json_bytes(path.read_bytes()), requested_model, model_spec)


def watermark_parameters() -> dict[str, Any]:
    return {
        "ngram_len": NGRAM_LEN,
        "keys": list(KEYS),
        "context_history_size": CONTEXT_HISTORY_SIZE,
        "sampling_table_seed": SAMPLING_TABLE_SEED,
        "sampling_table_size": TABLE_SIZE,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=sorted(MODELS), required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260815)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError(f"refusing to overwrite {args.output}")
    if not 5 <= args.max_new_tokens <= 1024:
        raise ValueError("max-new-tokens must be from 5 to 1024")

    import torch
    import transformers

    verify_runner_install(torch)
    torch.use_deterministic_algorithms(True)
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable")
    model_spec = MODELS[args.model]
    table = read_table(torch, device)

    class FixedTableWatermarkingConfig(transformers.SynthIDTextWatermarkingConfig):
        def construct_processor(self, vocab_size: int, target_device: Any) -> Any:
            processor = super().construct_processor(vocab_size, target_device)
            processor.sampling_table = table.to(target_device)
            return processor

    watermarking_config = FixedTableWatermarkingConfig(**watermark_parameters())

    token_ids = load_input(args.input, args.model, model_spec)

    torch.manual_seed(args.seed)
    model_class = getattr(transformers, model_spec["class"])
    model = model_class.from_pretrained(
        model_spec["repository"],
        revision=model_spec["revision"],
        dtype=torch.float32 if device.type == "cpu" else torch.bfloat16,
        use_safetensors=True,
        trust_remote_code=False,
    ).to(device)
    if type(model).__name__ != model_spec["class"]:
        raise ValueError(f"loaded unexpected model class {type(model).__name__}")
    model.eval()
    validate_vocabulary(token_ids, model.config.vocab_size)
    prompt = torch.tensor([token_ids], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(prompt)
    with torch.no_grad():
        output = model.generate(
            prompt,
            attention_mask=attention_mask,
            do_sample=True,
            temperature=0.5,
            top_k=40,
            watermarking_config=watermarking_config,
            max_new_tokens=args.max_new_tokens,
            pad_token_id=model.config.eos_token_id,
        )
    generated = output[0, len(token_ids):].to("cpu").tolist()
    trace = {
        "schema": "declawd.synthid-trace/v1",
        "trace_id": f"{args.model}-seed-{args.seed}",
        "profile": {
            "id": PROFILE_ID,
            "file_sha256": PROFILE_SHA256,
        },
        "sequence_role": "generated_output_only",
        "tokenizer": {
            "model_id": model_spec["repository"],
            "revision": model_spec["revision"],
            "eos_token_id": model.config.eos_token_id,
        },
        "token_ids": generated,
    }
    provisional = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace["expected"] = expected_from_report(score_trace(trace, provisional))
    with args.output.open("x", encoding="utf-8", newline="\n") as output_file:
        output_file.write(json.dumps(trace, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

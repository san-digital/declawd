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


ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "gpt2": {
        "repository": "openai-community/gpt2",
        "revision": "607a30d783dfa663caf39e06633721c8d4cfcd7e",
        "class": "SynthIDGPT2LMHeadModel",
    },
    "gemma-2b-it": {
        "repository": "google/gemma-2b-it",
        "revision": "96988410cbdaeb8d5093d1ebdc5a8fb563e02bad",
        "class": "SynthIDGemmaForCausalLM",
    },
}
SYNTHID_COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"


def verify_synthid_install() -> None:
    distribution = importlib.metadata.distribution("synthid-text")
    if distribution.version != "0.2.1":
        raise ValueError(f"expected synthid-text 0.2.1, found {distribution.version}")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    if direct_url.get("vcs_info", {}).get("commit_id") != SYNTHID_COMMIT:
        raise ValueError(f"synthid-text must be installed from commit {SYNTHID_COMMIT}")


def read_table(torch: Any, device: Any) -> Any:
    packed = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
    bits = [
        (packed[index // 8] >> (index % 8)) & 1
        for index in range(65_536)
    ]
    return torch.tensor(bits, dtype=torch.int64, device=device)


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
    from synthid_text import logits_processing, synthid_mixin

    verify_synthid_install()
    if torch.__version__.split("+", 1)[0] != "2.4.0":
        raise ValueError(f"expected torch 2.4.0, found {torch.__version__}")
    device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise ValueError("CUDA was requested but is unavailable")
    model_spec = MODELS[args.model]
    base_class = getattr(synthid_mixin, model_spec["class"])
    table = read_table(torch, device)

    class FixedTableModel(base_class):
        def _construct_warper_list(self, extra_params: dict[str, Any]) -> Any:
            config = dict(synthid_mixin.DEFAULT_WATERMARKING_CONFIG)
            config["device"] = device
            processor = logits_processing.SynthIDLogitsProcessor(
                **config, **extra_params
            )
            processor.sampling_table = table
            return __import__("transformers").LogitsProcessorList([processor])

    input_document = json.loads(args.input.read_text(encoding="utf-8"))
    expected_model = input_document.get("model")
    if expected_model != args.model:
        raise ValueError(f"input model {expected_model!r} does not match {args.model!r}")
    token_ids = input_document.get("prompt_token_ids")
    if not isinstance(token_ids, list) or not token_ids:
        raise ValueError("input requires a non-empty prompt_token_ids array")

    torch.manual_seed(args.seed)
    model = FixedTableModel.from_pretrained(
        model_spec["repository"],
        revision=model_spec["revision"],
        torch_dtype=torch.float32 if device.type == "cpu" else torch.bfloat16,
    ).to(device)
    model.eval()
    prompt = torch.tensor([token_ids], dtype=torch.long, device=device)
    attention_mask = torch.ones_like(prompt)
    with torch.no_grad():
        output = model.generate(
            prompt,
            attention_mask=attention_mask,
            do_sample=True,
            temperature=0.5,
            top_k=40,
            max_new_tokens=args.max_new_tokens,
            pad_token_id=model.config.eos_token_id,
        )
    generated = output[0, len(token_ids):].to("cpu").tolist()
    trace = {
        "schema": "declawd.synthid-trace/v1",
        "trace_id": f"{args.model}-seed-{args.seed}",
        "profile": {
            "id": "declawd.synthid-profile/v1",
            "file_sha256": "3fcb8947cc6e267a653196571d9e43434de405b2977838cf95167c94c0ac8e08",
        },
        "sequence_role": "generated_output_only",
        "tokenizer": {
            "model_id": model_spec["repository"],
            "revision": model_spec["revision"],
            "eos_token_id": model.config.eos_token_id,
        },
        "token_ids": generated,
    }
    from synthid_reference import expected_from_report, score_trace

    provisional = (json.dumps(trace, indent=2) + "\n").encode("utf-8")
    trace["expected"] = expected_from_report(score_trace(trace, provisional))
    args.output.write_text(json.dumps(trace, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

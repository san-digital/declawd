#!/usr/bin/env python3
"""Compare committed vectors with DeepMind's pinned 0.2.1 implementation."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthid_reference as exact

SYNTHID_COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"


def pack_lsb0(values: list[int]) -> bytes:
    packed = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        packed[index // 8] |= int(value) << (index % 8)
    return bytes(packed)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "trace",
        nargs="?",
        type=Path,
        default=ROOT / "fixtures/synthid/trace-prepared-v1.json",
    )
    args = parser.parse_args()

    import torch
    from synthid_text import logits_processing, synthid_mixin

    distribution = importlib.metadata.distribution("synthid-text")
    direct_url = json.loads(distribution.read_text("direct_url.json") or "{}")
    if distribution.version != "0.2.1" or direct_url.get("vcs_info", {}).get("commit_id") != SYNTHID_COMMIT:
        raise ValueError(f"synthid-text must be 0.2.1 from commit {SYNTHID_COMMIT}")
    if torch.__version__.split("+", 1)[0] != "2.4.0":
        raise ValueError(f"expected torch 2.4.0, found {torch.__version__}")
    config = dict(synthid_mixin.DEFAULT_WATERMARKING_CONFIG)
    config["device"] = torch.device("cpu")
    processor = logits_processing.SynthIDLogitsProcessor(
        **config, top_k=40, temperature=0.5
    )
    generated_table = pack_lsb0(processor.sampling_table.tolist())
    committed_table = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
    if generated_table != committed_table:
        raise RuntimeError("DeepMind CPU sampling table differs from the committed table")

    source = args.trace.read_bytes()
    trace = json.loads(source)
    tokens = torch.tensor([trace["token_ids"]], dtype=torch.long)
    if tokens.shape[1] < config["ngram_len"]:
        print("upstream comparison skipped: trace has no complete n-gram")
        return 0
    g_values = processor.compute_g_values(tokens)
    repetition = processor.compute_context_repetition_mask(tokens)
    eos_id = trace["tokenizer"]["eos_token_id"]
    if eos_id is None:
        eos = torch.ones_like(repetition)
    else:
        eos = processor.compute_eos_token_mask(tokens, eos_id)[:, config["ngram_len"] - 1:]
    mask = repetition * eos
    report = exact.score_trace(trace, source)
    valid_count = int(mask.sum().item())
    if valid_count != report["valid_context_count"]:
        raise RuntimeError("DeepMind valid mask differs from the exact reference")
    raw = float((g_values * mask[:, :, None]).sum().item() / (30 * valid_count))
    weights = torch.linspace(10, 1, 30)
    weights *= 30 / weights.sum()
    weighted = float(
        (g_values * weights[None, None, :] * mask[:, :, None]).sum().item()
        / (30 * valid_count)
    )
    if abs(raw - float(report["raw_score"]["decimal"])) > 1e-6:
        raise RuntimeError("DeepMind raw mean differs by more than 1e-6")
    if abs(weighted - float(report["weighted_score"]["decimal"])) > 1e-6:
        raise RuntimeError("DeepMind weighted mean differs by more than 1e-6")
    print("verified exact vectors against google-deepmind/synthid-text 0.2.1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

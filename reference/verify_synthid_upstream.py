#!/usr/bin/env python3
"""Compare exact and maintained runtimes with DeepMind's pinned public source."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import synthid_reference as exact


SYNTHID_COMMIT = "8f2e2316904ea7291ac96e30eb394c453dcc577b"
RUNTIME = {
    "jax": "0.11.0",
    "jaxlib": "0.11.0",
    "torch": "2.13.0",
    "transformers": "5.15.0",
}


def pack_lsb0(values: list[int]) -> bytes:
    packed = bytearray((len(values) + 7) // 8)
    for index, value in enumerate(values):
        packed[index // 8] |= int(value) << (index % 8)
    return bytes(packed)


def digest(values: list[int]) -> dict[str, object]:
    packed = pack_lsb0(values)
    return {
        "bit_length": len(values),
        "byte_length": len(packed),
        "sha256": hashlib.sha256(packed).hexdigest(),
    }


def verify_runtime() -> None:
    installed = {
        name: importlib.metadata.version(name).split("+", 1)[0]
        for name in RUNTIME
    }
    if installed != RUNTIME:
        raise ValueError(f"expected oracle runtime {RUNTIME}, found {installed}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--upstream", type=Path, required=True)
    parser.add_argument(
        "--trace",
        type=Path,
        default=ROOT / "fixtures/synthid/trace-prepared-v1.json",
    )
    args = parser.parse_args()
    upstream = args.upstream.resolve()
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=upstream, text=True
    ).strip()
    if commit != SYNTHID_COMMIT:
        raise ValueError(f"upstream source must be at commit {SYNTHID_COMMIT}")
    if subprocess.run(
        ["git", "symbolic-ref", "-q", "HEAD"], cwd=upstream,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    ).returncode == 0:
        raise ValueError("upstream source must be a detached immutable checkout")
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=upstream,
        text=True,
    )
    if status:
        raise ValueError("upstream source checkout must be clean with no untracked files")
    upstream_source = upstream / "src"
    if not upstream_source.is_dir():
        raise ValueError("upstream source checkout has no src directory")
    sys.path.insert(0, str(upstream_source))

    import jax.numpy as jnp
    import torch
    import transformers
    import synthid_text
    from synthid_text import detector_mean, logits_processing

    package_paths = [Path(path).resolve() for path in synthid_text.__path__]
    if package_paths != [(upstream_source / "synthid_text").resolve()]:
        raise ValueError("imported synthid_text namespace outside the pinned checkout")
    for module in (detector_mean, logits_processing):
        module_path = Path(module.__file__).resolve()
        if not module_path.is_relative_to(upstream_source):
            raise ValueError(f"imported {module.__name__} outside the pinned checkout")

    verify_runtime()
    profile = json.loads((ROOT / "fixtures/synthid/profile-v1.json").read_text())
    if tuple(profile["parameters"]["keys"]) != exact.KEYS:
        raise RuntimeError("profile keys differ from the exact reference")
    config = {
        "ngram_len": 5,
        "keys": list(exact.KEYS),
        "sampling_table_size": 65_536,
        "sampling_table_seed": 0,
        "context_history_size": 1024,
        "device": torch.device("cpu"),
    }
    table_bytes = (ROOT / "fixtures/synthid/sampling-table-v1.bin").read_bytes()
    table = torch.tensor(
        [
            (table_bytes[index // 8] >> (index % 8)) & 1
            for index in range(65_536)
        ],
        dtype=torch.int64,
    )

    upstream_processor = logits_processing.SynthIDLogitsProcessor(
        **config, top_k=40, temperature=0.5
    )
    upstream_processor.sampling_table = table
    maintained_config = transformers.SynthIDTextWatermarkingConfig(
        ngram_len=5,
        keys=list(exact.KEYS),
        sampling_table_size=65_536,
        sampling_table_seed=0,
        context_history_size=1024,
    )
    maintained_processor = maintained_config.construct_processor(50_257, torch.device("cpu"))
    maintained_processor.sampling_table = table

    source = args.trace.read_bytes()
    trace = json.loads(source)
    tokens = torch.tensor([trace["token_ids"]], dtype=torch.long)
    if tokens.shape[1] < 5:
        raise ValueError("compatibility oracle requires at least one complete n-gram")
    upstream_g = upstream_processor.compute_g_values(tokens)
    maintained_g = maintained_processor.compute_g_values(tokens)
    if not torch.equal(upstream_g, maintained_g):
        raise RuntimeError("maintained runtime g-values differ from DeepMind 0.2.1")
    upstream_repetition = upstream_processor.compute_context_repetition_mask(tokens)
    maintained_repetition = maintained_processor.compute_context_repetition_mask(tokens)
    if not torch.equal(upstream_repetition, maintained_repetition):
        raise RuntimeError("maintained repetition mask differs from DeepMind 0.2.1")
    eos_id = trace["tokenizer"]["eos_token_id"]
    if eos_id is None:
        upstream_eos = torch.ones_like(upstream_repetition)
        maintained_eos = torch.ones_like(maintained_repetition)
    else:
        upstream_eos = upstream_processor.compute_eos_token_mask(tokens, eos_id)[:, 4:]
        maintained_eos = maintained_processor.compute_eos_token_mask(tokens, eos_id)[:, 4:]
    if not torch.equal(upstream_eos, maintained_eos):
        raise RuntimeError("maintained EOS mask differs from DeepMind 0.2.1")
    upstream_valid = upstream_repetition * upstream_eos
    maintained_valid = maintained_repetition * maintained_eos
    if not torch.equal(upstream_valid, maintained_valid):
        raise RuntimeError("maintained valid mask differs from DeepMind 0.2.1")

    report = exact.score_trace(trace, source)
    g_rows = upstream_g.to(torch.int64).reshape(-1).tolist()
    repetition = upstream_repetition.to(torch.int64).reshape(-1).tolist()
    eos = upstream_eos.to(torch.int64).reshape(-1).tolist()
    valid = upstream_valid.to(torch.int64).reshape(-1).tolist()
    if digest(g_rows) != report["g_values"]:
        raise RuntimeError("DeepMind row-major g digest differs from the exact report")
    if digest(repetition) != report["masks"]["repetition"]:
        raise RuntimeError("DeepMind repetition digest differs from the exact report")
    if digest(eos) != report["masks"]["eos"]:
        raise RuntimeError("DeepMind EOS digest differs from the exact report")
    if digest(valid) != report["masks"]["valid"]:
        raise RuntimeError("DeepMind valid digest differs from the exact report")

    g_jax = jnp.asarray(upstream_g.cpu().numpy())
    mask_jax = jnp.asarray(upstream_valid.cpu().numpy())
    jax_raw = float(detector_mean.mean_score(g_jax, mask_jax)[0])
    jax_weighted = float(
        detector_mean.weighted_mean_score(g_jax.copy(), mask_jax)[0]
    )
    if abs(jax_raw - float(report["raw_score"]["decimal"])) > 1e-6:
        raise RuntimeError("DeepMind detector_mean.mean_score differs by more than 1e-6")
    if abs(jax_weighted - float(report["weighted_score"]["decimal"])) > 1e-6:
        raise RuntimeError(
            "DeepMind detector_mean.weighted_mean_score differs by more than 1e-6"
        )
    print(
        "verified DeepMind 0.2.1 and maintained-runtime g-values, repetition/EOS/valid "
        "masks, exact digests, and JAX mean/weighted_mean scores"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

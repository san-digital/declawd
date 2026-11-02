#!/usr/bin/env python3
"""Register future experiment inputs and record one seed after a committed preflight."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import tempfile

import future_candidate_review

SCHEMA = "declawd.future-registration/v1"
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
JOIN = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz'")
ENGINE_FILES = ("future_registration.py", "future_candidate_review.py", "test_future_registration.py")
CONFIG_FIELDS = {"profile_id", "template", "review", "corpus", "minimum_effective_tokens", "inputs", "registration", "seed", "outputs"}


def encoded(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError) as error:
        raise ValueError(f"could not read JSON object {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return value


def safe_path(root: Path, name: str) -> Path:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name:
        raise ValueError(f"invalid relative path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or str(path) != name or any(part in (".", "..") for part in path.parts):
        raise ValueError(f"invalid relative path: {name!r}")
    target = root / name
    if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"path must remain inside the experiment without a file symlink: {name}")
    return target


def git(top: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=top, stderr=subprocess.PIPE)


def repository(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()


def config(root: Path, name: str) -> dict:
    value = read_object(safe_path(root, name))
    if set(value) != CONFIG_FIELDS:
        raise ValueError("configuration fields differ from the documented schema")
    profile_id = value["profile_id"]
    if not isinstance(profile_id, str) or re.fullmatch(r"declawd-v[1-9][0-9]*(?:-[a-z0-9]+)*", profile_id) is None:
        raise ValueError("invalid profile_id")
    minimum = value["minimum_effective_tokens"]
    if type(minimum) is not int or minimum < 1:
        raise ValueError("minimum_effective_tokens must be a positive integer")
    if not isinstance(value["inputs"], list) or not value["inputs"]:
        raise ValueError("declare the plan, scoring procedure and other experiment inputs")
    if not isinstance(value["outputs"], list) or not value["outputs"]:
        raise ValueError("declare the complete output set")
    if any(not isinstance(value[key], str) for key in ("template", "review", "corpus", "registration", "seed")) or any(not isinstance(path, str) for path in [*value["inputs"], *value["outputs"]]):
        raise ValueError("every configured path must be a relative path string")
    sources = [name, value["template"], value["review"], value["corpus"], *value["inputs"]]
    if len(set(sources)) != len(sources):
        raise ValueError("configuration and input paths must be distinct")
    destinations = [value["registration"], value["seed"], value["seed"] + ".attempt.json", *value["outputs"]]
    if len(set(destinations)) != len(destinations) or set(sources) & set(destinations):
        raise ValueError("registration, seed, attempt, inputs and outputs must be distinct")
    for path in [*sources, *destinations]:
        safe_path(root, path)
    return value


def count_contexts(text: str) -> int:
    previous = ""
    pairs = set()
    for token in TOKEN.findall(text):
        current = token.lower()
        pairs.add((previous, current))
        previous = current
    return len(pairs)


def literal_bound(segments: list) -> int:
    """Coalesce literal runs and require unchanged token boundaries around every slot."""
    merged = []
    for segment in segments:
        if isinstance(segment, str):
            if not segment:
                continue
            if merged and isinstance(merged[-1], str):
                merged[-1] += segment
            else:
                merged.append(segment)
        else:
            merged.append(segment)
    for index, segment in enumerate(merged):
        if isinstance(segment, str):
            continue
        if index and (not isinstance(merged[index - 1], str) or merged[index - 1][-1] in JOIN):
            raise ValueError("candidate needs a token separator before its slot")
        if index + 1 < len(merged) and (not isinstance(merged[index + 1], str) or merged[index + 1][0] in JOIN):
            raise ValueError("candidate needs a token separator after its slot")
    pairs = set()
    for index, segment in enumerate(merged):
        if isinstance(segment, str):
            tokens = [token.lower() for token in TOKEN.findall(segment)]
            pairs.update(zip(tokens, tokens[1:]))
            if index == 0 and tokens:
                pairs.add(("", tokens[0]))
    return len(pairs)


def preflight(root: Path, config_name: str) -> tuple[dict, dict]:
    root = root.resolve()
    value = config(root, config_name)
    template_path = safe_path(root, value["template"])
    template = read_object(template_path)
    fixture = template.get("fixture_id")
    if not isinstance(fixture, str) or not fixture.strip() or fixture != fixture.strip():
        raise ValueError("template fixture_id must be a non-empty trimmed string")
    segments = future_candidate_review._segments(template)
    bound = literal_bound(segments)
    floor = value["minimum_effective_tokens"] + 1
    if bound < floor:
        raise ValueError(f"guaranteed literal pairs {bound} are below the required floor {floor}")
    future_candidate_review.validate(template_path, safe_path(root, value["review"]))
    control = count_contexts("".join(part if isinstance(part, str) else part[0] for part in segments))
    corpus = read_object(safe_path(root, value["corpus"])).get("passages")
    if not isinstance(corpus, list) or not corpus:
        raise ValueError("corpus passages must be a non-empty list")
    identifiers = set()
    authors = {"calibration": set(), "evaluation": set()}
    eligible = {"calibration": 0, "evaluation": 0}
    for passage in corpus:
        if not isinstance(passage, dict) or any(not isinstance(passage.get(key), str) or not passage[key] for key in ("id", "author", "split", "text")):
            raise ValueError("each corpus passage needs non-empty id, author, split and text")
        if passage["id"] in identifiers or passage["split"] not in authors:
            raise ValueError("corpus identifiers must be unique and splits known")
        identifiers.add(passage["id"])
        authors[passage["split"]].add(passage["author"])
        eligible[passage["split"]] += count_contexts(passage["text"]) >= floor
    if any(not count for count in eligible.values()) or authors["calibration"] & authors["evaluation"]:
        raise ValueError("separate calibration and evaluation authors must cover every boundary")
    top = repository(root)
    prefix = root.relative_to(top)
    own_directory = Path(__file__).resolve().parent
    engine = [own_directory / name for name in ENGINE_FILES]
    sources = [safe_path(root, name) for name in (config_name, value["template"], value["review"], value["corpus"], *value["inputs"])] + engine
    try:
        files = {path.relative_to(top).as_posix(): sha256(path.read_bytes()) for path in sources}
    except ValueError as error:
        raise ValueError("run the checked-in registration tool from the experiment repository") from error
    receipt = {
        "schema": SCHEMA, "profile_id": value["profile_id"],
        "domain_separator": "declawd/" + value["profile_id"][8:] + "/green",
        "experiment_root": prefix.as_posix(), "configuration": config_name,
        "tokeniser_pattern": TOKEN.pattern, "fixture_id": fixture,
        "minimum_effective_tokens": value["minimum_effective_tokens"],
        "required_pair_floor": floor, "guaranteed_literal_pairs": bound,
        "control_pairs": control, "source_files": files,
    }
    return value, receipt


def require_committed(top: Path, names: list[str], revision: str | None = None) -> str:
    revision = revision or git(top, "rev-parse", "HEAD").decode().strip()
    for name in names:
        if git(top, "show", f"{revision}:{name}") != (top / name).read_bytes():
            raise ValueError(f"commit the exact registered bytes: {name}")
        if git(top, "diff", "--cached", "--", name):
            raise ValueError(f"registered file has staged changes: {name}")
    return revision


def atomic_json(path: Path, value: dict, *, replace: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + "-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def attempt_path(root: Path, value: dict) -> Path:
    return safe_path(root, value["seed"] + ".attempt.json")


def refuse_existing(root: Path, value: dict, *, registration: bool = False) -> None:
    paths = [value["seed"], value["seed"] + ".attempt.json", *value["outputs"]]
    if registration:
        paths.append(value["registration"])
    if any(os.path.lexists(root / name) for name in paths):
        raise ValueError("a registration, seed, attempt or output already exists")


def register(root: Path, config_name: str) -> dict:
    root = root.resolve()
    value, receipt = preflight(root, config_name)
    refuse_existing(root, value, registration=True)
    top = repository(root)
    destination = safe_path(root, value["registration"])
    for name in git(top, "ls-files", "-z", "*registration*.json").decode().split("\0"):
        if name and top / name != destination:
            other = read_object(top / name)
            if other.get("registration_id") == value["profile_id"] or (other.get("schema") == SCHEMA and other.get("profile_id") == value["profile_id"]):
                raise ValueError("profile_id already has a tracked registration")
    receipt["inputs_commit"] = require_committed(top, list(receipt["source_files"]))
    atomic_json(destination, receipt)
    return receipt


def verify_receipt(root: Path, config_name: str) -> tuple[dict, dict]:
    root = root.resolve()
    value, expected = preflight(root, config_name)
    path = safe_path(root, value["registration"])
    receipt = read_object(path)
    original_commit = receipt.get("inputs_commit")
    if not isinstance(original_commit, str) or re.fullmatch(r"[0-9a-f]{40}", original_commit) is None:
        raise ValueError("registration needs its complete inputs commit")
    if path.read_bytes() != encoded(receipt) or receipt != {**expected, "inputs_commit": original_commit}:
        raise ValueError("registration receipt, preflight or bound inputs changed")
    top = repository(root)
    require_committed(top, list(expected["source_files"]), original_commit)
    require_committed(top, [*expected["source_files"], path.relative_to(top).as_posix()])
    git(top, "merge-base", "--is-ancestor", original_commit, "HEAD")
    return value, receipt


def sample(root: Path, config_name: str) -> dict:
    root = root.resolve()
    value, receipt = verify_receipt(root, config_name)
    refuse_existing(root, value)
    top = repository(root)
    registration_commit = git(top, "rev-parse", "HEAD").decode().strip()
    marker = {"profile_id": receipt["profile_id"], "registration_sha256": sha256(encoded(receipt)), "registration_commit": registration_commit, "started_at": datetime.now(timezone.utc).isoformat()}
    atomic_json(attempt_path(root, value), marker)
    seed = {**marker, "attempt_sha256": sha256(encoded(marker)), "seed_hex": secrets.token_bytes(32).hex()}
    atomic_json(safe_path(root, value["seed"]), seed)
    return seed


def verified_seed(root: Path, config_name: str) -> tuple[dict, dict, dict]:
    root = root.resolve()
    value, receipt = verify_receipt(root, config_name)
    seed_path = safe_path(root, value["seed"])
    seed = read_object(seed_path)
    marker_path = attempt_path(root, value)
    marker = read_object(marker_path)
    if marker_path.read_bytes() != encoded(marker) or set(marker) != {"profile_id", "registration_sha256", "registration_commit", "started_at"} or marker.get("profile_id") != receipt["profile_id"]:
        raise ValueError("attempt record is not canonical or has unexpected fields")
    if seed_path.read_bytes() != encoded(seed) or set(seed) != {*marker, "attempt_sha256", "seed_hex"}:
        raise ValueError("seed record is not canonical or has unexpected fields")
    if any(seed.get(key) != item for key, item in marker.items()) or marker.get("registration_sha256") != sha256(encoded(receipt)) or seed["attempt_sha256"] != sha256(encoded(marker)):
        raise ValueError("seed or attempt differs from the registration")
    try:
        if len(bytes.fromhex(seed["seed_hex"])) != 32:
            raise ValueError("seed must contain 32 bytes")
    except (TypeError, ValueError) as error:
        raise ValueError("seed must contain 32 bytes") from error
    top = repository(root)
    seed_name = seed_path.relative_to(top).as_posix()
    require_committed(top, [seed_name, attempt_path(root, value).relative_to(top).as_posix()])
    require_committed(top, [safe_path(root, value["registration"]).relative_to(top).as_posix()], seed["registration_commit"])
    first = git(top, "log", "--reverse", "--format=%H", "--diff-filter=A", "--", seed_name).decode().splitlines()[0]
    if git(top, "show", f"{first}:{seed_name}") != seed_path.read_bytes():
        raise ValueError("seed differs from its first committed draw")
    git(top, "merge-base", "--is-ancestor", seed["registration_commit"], first)
    if first == seed["registration_commit"]:
        raise ValueError("commit registration before the seed")
    binding = {"registration_sha256": sha256(encoded(receipt)), "seed_hex": seed["seed_hex"], "seed_record_sha256": sha256(encoded(seed))}
    for name in value["outputs"]:
        path = safe_path(root, name)
        if path.exists():
            existing = read_object(path)
            if any(existing.get(key) != item for key, item in binding.items()):
                raise ValueError(f"surviving output has a different seed binding: {name}")
    return value, seed, binding


def write_outputs(root: Path, config_name: str, documents: dict[str, dict]) -> None:
    value, _, binding = verified_seed(root, config_name)
    if set(documents) != set(value["outputs"]) or any(not isinstance(document, dict) for document in documents.values()):
        raise ValueError("provide the complete declared output set")
    if any(any(document.get(key) != item for key, item in binding.items()) for document in documents.values()):
        raise ValueError("every output must retain the verified seed binding")
    for name, document in documents.items():
        atomic_json(safe_path(root, name), document, replace=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("register", "sample", "verify"))
    parser.add_argument("root", type=Path)
    parser.add_argument("configuration")
    args = parser.parse_args()
    try:
        if args.command == "register":
            register(args.root, args.configuration)
        elif args.command == "sample":
            sample(args.root, args.configuration)
        else:
            verified_seed(args.root, args.configuration)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"[failed] {error}\n")
    print(f"[ok] future experiment {args.command}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

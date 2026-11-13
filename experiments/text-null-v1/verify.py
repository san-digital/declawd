from pathlib import Path
import gzip
import json
import math
from study import generate, sha, verify_registration


def compare(actual, expected, path="result"):
    if type(actual) is not type(expected):
        raise ValueError(f"{path}: type differs")
    if isinstance(expected, dict):
        if actual.keys() != expected.keys():
            raise ValueError(f"{path}: keys differ")
        for key in expected:
            compare(actual[key], expected[key], path + "." + key)
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            raise ValueError(f"{path}: length differs")
        for index, (value, recorded) in enumerate(zip(actual, expected)):
            compare(value, recorded, f"{path}[{index}]")
    elif isinstance(expected, float):
        if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"{path}: numerical value differs: {actual} versus {expected}")
    elif actual != expected:
        raise ValueError(f"{path}: discrete outcome differs: {actual} versus {expected}")


def main():
    root = Path(__file__).resolve().parent
    verify_registration()
    expected = json.loads(gzip.decompress((root / "results.json.gz").read_bytes()))
    actual = generate()
    actual["registration_sha256"] = sha(root / "registration.json")
    actual["python"] = expected["python"]
    for value, recorded in zip(actual["documents"], expected["documents"]):
        for pivot, frozen, marked in zip(value["pivots"], recorded["pivots"], recorded["labels"]):
            tolerance = max(math.ulp(pivot), math.ulp(frozen)) if marked else 0.0
            if abs(pivot - frozen) > tolerance:
                raise ValueError("Registered pivot draws differ beyond cubing round-off")
    compare(actual, expected)
    if len(expected["documents"]) != 300 or len(expected["prevalence"]) != 40:
        raise ValueError("The result set is incomplete")
    print("Verified all 300 documents, 624000 intervals and 40 prevalence records; null pivots and discrete decisions exact, cubed pivots within one ULP, derived floats within 1e-12")


if __name__ == "__main__":
    main()

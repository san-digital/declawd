from pathlib import Path
import gzip
import json
from study import generate, sha, verify_registration


root = Path(__file__).resolve().parent
verify_registration()
expected = json.loads(gzip.decompress((root / "results.json.gz").read_bytes()))
actual = generate()
actual["registration_sha256"] = sha(root / "registration.json")
actual["python"] = expected["python"]
if actual != expected:
    raise SystemExit("Registered outcomes differ from the complete result")
if len(expected["documents"]) != 300 or len(expected["prevalence"]) != 80:
    raise SystemExit("The result set is incomplete")
print("Verified all 300 documents, 624000 intervals and 80 prevalence records")

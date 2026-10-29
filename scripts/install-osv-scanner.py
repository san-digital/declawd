#!/usr/bin/env python3
import hashlib
from pathlib import Path
import platform
import sys
from urllib.request import urlopen


VERSION = "2.7.0"
ASSETS = {
    ("Linux", "x86_64"): (
        "linux_amd64",
        "160c6253e2922e9e0a6a9771c5c4c40a4b3c6090b34a3cdd5e80c96cc2e4218b",
    ),
    ("Darwin", "arm64"): (
        "darwin_arm64",
        "d4926ef8da134332543be276dff157e4c170f99ad91fc48e89448a8816bdf70b",
    ),
}


def main():
    asset, digest = ASSETS[(platform.system(), platform.machine())]
    url = f"https://github.com/google/osv-scanner/releases/download/v{VERSION}/osv-scanner_{asset}"
    with urlopen(url, timeout=120) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("OSV-Scanner release checksum mismatch")
    output = Path(sys.argv[1])
    output.write_bytes(data)
    output.chmod(0o755)
    print(f"installed verified OSV-Scanner {VERSION}: {output}")


if __name__ == "__main__":
    main()

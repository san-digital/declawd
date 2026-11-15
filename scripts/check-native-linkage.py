#!/usr/bin/env python3
"""Reject binary dependencies on external OpenSSL libraries."""
import argparse
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument("binary")
parser.add_argument("--target", required=True)
args = parser.parse_args()
if "apple-darwin" in args.target:
    command = ["otool", "-L", args.binary]
elif "windows-msvc" in args.target:
    command = ["dumpbin", "/dependents", args.binary]
else:
    command = ["ldd", args.binary]
result = subprocess.check_output(command, text=True)
if "libssl" in result.lower() or "libcrypto" in result.lower():
    raise ValueError(f"binary depends on an external OpenSSL library: {result}")
print(result)
print("verified static OpenSSL linkage")

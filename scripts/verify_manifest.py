#!/usr/bin/env python3
"""Verify-before-run integrity check (playbook §2 boot-manifest pattern, issue B1).

Compares sha256 of each file listed in monitor/manifest.json against the file on
disk. On any mismatch: stop and report (exit 1) — never proceed on a stale store.
Regenerate the manifest after intentional changes: python3 scripts/verify_manifest.py --update
"""
import hashlib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "monitor", "manifest.json")


def sha256_of(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main() -> int:
    with open(MANIFEST) as f:
        manifest = json.load(f)
    if "--update" in sys.argv:
        for entry in manifest["files"]:
            entry["sha256"] = sha256_of(os.path.join(ROOT, entry["path"]))
        with open(MANIFEST, "w") as f:
            json.dump(manifest, f, indent=2)
        print("manifest updated")
        return 0
    ok = True
    for entry in manifest["files"]:
        path = os.path.join(ROOT, entry["path"])
        actual = sha256_of(path)
        status = "OK" if actual == entry["sha256"] else "MISMATCH"
        if actual != entry["sha256"]:
            ok = False
        print(f"{status}  {entry['path']}  expected={entry['sha256'][:12]} actual={actual[:12]}")
    if not ok:
        print("STOP: manifest mismatch — do not run on a stale store.", file=sys.stderr)
        return 1
    print("manifest OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

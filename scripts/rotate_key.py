#!/usr/bin/env python3
"""Generate a replacement signing key and print the coordinated replacement procedure.

This script does NOT perform the committee/node replacement: key rotation requires
coordination with the committee and deployment configuration.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from crypto.identity import Identity


def check_permissions(path: Path) -> None:
    if path.exists() and (path.stat().st_mode & 0o077):
        raise ValueError(
            f"KEY FILE IS READABLE BY OTHERS: {path}. "
            f"Remediation: chmod 600 {path} (do not auto-correct)."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", required=True, help="Path to the current signing key file")
    parser.add_argument("--new", required=True, help="Path for the new signing key file")
    args = parser.parse_args()

    old = Path(args.old)
    new = Path(args.new)

    if old.exists():
        check_permissions(old)
        # Verify it is loadable (permissions already checked)
        Identity.load(old)

    if new.exists():
        raise ValueError(f"NEW KEY PATH ALREADY EXISTS: {new}")

    identity = Identity.create()
    identity.save(new)

    mode = stat.S_IMODE(new.stat().st_mode)
    if mode != 0o600:
        os.chmod(new, 0o600)
        mode = 0o600

    print(f"new_key_path={new}")
    print(f"new_key_mode={oct(mode)}")
    print(f"new_public_key={identity.public_key.hex()}")
    print(f"new_identity_id={identity.identity_id}")
    print()
    print("COORDINATED REPLACEMENT PROCEDURE (do not execute automatically):")
    print(f"1. Verify permissions: ls -l {new} (must be -rw------- / 0600).")
    print("2. Securely distribute the new public key/identity to the committee/governance process.")
    print("3. Schedule a committee/config change that authorizes the replacement key according to protocol rules.")
    print(f"4. Update node/deployment configuration to reference {new} only after the committee accepts the change.")
    print("5. Restart/redeploy affected nodes in a coordinated window; monitor certificates, quorum, and audit logs.")
    print(f"6. Revoke/retire the old key material ({old}) only after the new key is active and stable.")
    print("7. Keep backups of key metadata and rotation records; never store private keys in logs or tickets.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)

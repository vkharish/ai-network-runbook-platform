"""
Credential encryption key rotation script.

Use this when rotating CREDENTIAL_ENCRYPTION_KEY in .env.

Steps:
  1. Set OLD_CREDENTIAL_KEY=<old value> in environment
  2. Set CREDENTIAL_ENCRYPTION_KEY=<new value> in .env
  3. Run: python3 scripts/rotate_credential_key.py
  4. Restart the API and worker

Usage:
  OLD_CREDENTIAL_KEY="old-key-value" python3 scripts/rotate_credential_key.py

Dry run (no DB writes):
  OLD_CREDENTIAL_KEY="old-key-value" python3 scripts/rotate_credential_key.py --dry-run
"""

import asyncio
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _make_fernet(key_str: str):
    from cryptography.fernet import Fernet
    raw = hashlib.sha256(key_str.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


async def rotate(dry_run: bool = False) -> None:
    old_key_str = os.environ.get("OLD_CREDENTIAL_KEY", "").strip()
    if not old_key_str:
        print("ERROR: Set OLD_CREDENTIAL_KEY environment variable to the previous key value.")
        sys.exit(1)

    from backend.core.config import settings
    new_key_str = settings.credential_encryption_key

    if old_key_str == new_key_str:
        print("OLD_CREDENTIAL_KEY and CREDENTIAL_ENCRYPTION_KEY are identical — nothing to do.")
        sys.exit(0)

    old_fernet = _make_fernet(old_key_str)
    new_fernet = _make_fernet(new_key_str)

    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy import select, update
    from backend.models.device_model import Device, DeviceCredential

    engine = create_async_engine(settings.database_url, echo=False)
    AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with AsyncSessionLocal() as db:
        # ── 1. Rotate device_credentials ────────────────────────────────────
        result = await db.execute(select(DeviceCredential))
        creds = result.scalars().all()
        print(f"Found {len(creds)} device credential(s).")

        for cred in creds:
            try:
                plaintext = old_fernet.decrypt(cred.password_encrypted.encode()).decode()
            except Exception:
                print(f"  [SKIP] DeviceCredential {cred.id} — cannot decrypt with old key (already rotated?)")
                continue

            new_encrypted = new_fernet.encrypt(plaintext.encode()).decode()

            if dry_run:
                print(f"  [DRY-RUN] Would re-encrypt DeviceCredential {cred.id} (device_id={cred.device_id})")
            else:
                cred.password_encrypted = new_encrypted
                print(f"  [OK] Re-encrypted DeviceCredential {cred.id} (device_id={cred.device_id})")

        # ── 2. Rotate jump host passwords inside devices.jump_hosts JSONB ───
        result = await db.execute(select(Device))
        devices = result.scalars().all()
        print(f"Found {len(devices)} device(s).")

        for device in devices:
            jump_hosts = device.jump_hosts or []
            if not jump_hosts:
                continue

            updated_hops = []
            changed = False
            for hop in jump_hosts:
                hop = dict(hop)
                enc = hop.get("password_encrypted", "")
                if not enc:
                    updated_hops.append(hop)
                    continue
                try:
                    plaintext = old_fernet.decrypt(enc.encode()).decode()
                except Exception:
                    print(f"  [SKIP] Jump hop {hop.get('host')} on device {device.hostname} — cannot decrypt")
                    updated_hops.append(hop)
                    continue

                hop["password_encrypted"] = new_fernet.encrypt(plaintext.encode()).decode()
                updated_hops.append(hop)
                changed = True

            if changed:
                if dry_run:
                    print(f"  [DRY-RUN] Would re-encrypt {len(updated_hops)} jump hop(s) on {device.hostname}")
                else:
                    device.jump_hosts = updated_hops
                    print(f"  [OK] Re-encrypted jump hosts on {device.hostname}")

        if dry_run:
            print("\nDry run complete — no changes written.")
        else:
            await db.commit()
            print("\nRotation complete — all credentials re-encrypted with new key.")

    await engine.dispose()


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(rotate(dry_run=dry_run))

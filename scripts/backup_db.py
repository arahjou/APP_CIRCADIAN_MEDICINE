from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from cryptography.fernet import Fernet


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _sqlite_integrity_ok(db_path: Path) -> bool:
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("PRAGMA integrity_check;").fetchone()
    return bool(row and str(row[0]).lower() == "ok")


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    _load_dotenv(project_root / ".env")

    parser = argparse.ArgumentParser(description="Encrypted SQLite backup with integrity check")
    parser.add_argument("--db", default=os.getenv("DB_PATH", "Actigraph_record.db"))
    parser.add_argument("--out-dir", default="backups")
    parser.add_argument("--key", default=os.getenv("DB_BACKUP_KEY", ""))
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return 1

    if not _sqlite_integrity_ok(db_path):
        print("Integrity check failed; backup aborted")
        return 2

    if not args.key:
        print("DB_BACKUP_KEY (or --key) is required for encrypted backups")
        return 3

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = out_dir / f"actigraph_{ts}.db.enc"

    cipher = Fernet(_derive_fernet_key(args.key))
    plaintext = db_path.read_bytes()
    ciphertext = cipher.encrypt(plaintext)
    backup_file.write_bytes(ciphertext)

    print(f"Backup written: {backup_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

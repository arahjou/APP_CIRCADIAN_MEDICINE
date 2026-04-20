from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running this file directly via `python scripts/bootstrap_admin.py`.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def main() -> int:
    from tools.database import ActigraphDB
    from tools.settings import get_settings

    parser = argparse.ArgumentParser(description="Create or rotate an admin user")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    args = parser.parse_args()

    settings = get_settings()
    db = ActigraphDB(db_path=settings.db_path)
    ok = db.create_or_update_user(args.username, args.password, role="admin")
    if not ok:
        print("Failed to create/update admin user")
        return 1

    db.add_audit_log(
        event_type="admin_bootstrap",
        username=args.username,
        details={"role": "admin"},
    )
    print(f"Admin user '{args.username}' is ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

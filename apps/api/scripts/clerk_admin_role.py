"""Manage Tenzo admin roles directly via the Clerk Backend API.

Avoids having to click through dashboard.clerk.com — useful when the Clerk
developer dashboard isn't handy (or when you need to batch-update users).

Commands:
    python /app/scripts/clerk_admin_role.py list
    python /app/scripts/clerk_admin_role.py grant <user_id>
    python /app/scripts/clerk_admin_role.py revoke <user_id>
    python /app/scripts/clerk_admin_role.py grant-by-email <email>

Requires CLERK_SECRET_KEY in env (already set in docker-compose.yml).
"""

from __future__ import annotations

import os
import sys
from typing import Optional

import httpx

CLERK_API = "https://api.clerk.com/v1"
CLERK_SECRET = os.environ.get("CLERK_SECRET_KEY", "")
if not CLERK_SECRET:
    print("ERROR: CLERK_SECRET_KEY env var not set.", file=sys.stderr)
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {CLERK_SECRET}",
    "Content-Type": "application/json",
}


def list_users() -> list[dict]:
    r = httpx.get(f"{CLERK_API}/users", headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.json()


def find_user_by_email(email: str) -> Optional[dict]:
    email = email.strip().lower()
    for u in list_users():
        for e in u.get("email_addresses") or []:
            if e.get("email_address", "").lower() == email:
                return u
    return None


def set_role(user_id: str, role: Optional[str]) -> dict:
    """Patch public_metadata.role on the given user.

    Passing role=None removes the role entirely.
    """
    payload = {"public_metadata": {"role": role} if role else {"role": None}}
    r = httpx.patch(
        f"{CLERK_API}/users/{user_id}/metadata",
        headers=HEADERS,
        json=payload,
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def print_users() -> None:
    print(f"{'user_id':<35} {'email':<40} {'name':<25} role")
    print("-" * 110)
    for u in list_users():
        email = (u.get("email_addresses") or [{}])[0].get("email_address", "—")
        first = u.get("first_name") or ""
        last = u.get("last_name") or ""
        name = f"{first} {last}".strip() or u.get("username", "—")
        role = (u.get("public_metadata") or {}).get("role") or "—"
        marker = "  ← admin" if role == "tenzo_admin" else ""
        print(f"{u['id']:<35} {email:<40} {name:<25} {role}{marker}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    cmd = sys.argv[1]

    if cmd == "list":
        print_users()
        return 0

    if cmd in ("grant", "revoke"):
        if len(sys.argv) < 3:
            print(f"Usage: python {sys.argv[0]} {cmd} <user_id>", file=sys.stderr)
            return 2
        user_id = sys.argv[2]
        role = "tenzo_admin" if cmd == "grant" else None
        set_role(user_id, role)
        action = "granted" if cmd == "grant" else "revoked"
        print(f"✓ {action} tenzo_admin for {user_id}")
        print()
        print("NEXT: sign out and back in on http://localhost:3000 to refresh your session.")
        return 0

    if cmd == "grant-by-email":
        if len(sys.argv) < 3:
            print(f"Usage: python {sys.argv[0]} grant-by-email <email>", file=sys.stderr)
            return 2
        email = sys.argv[2]
        user = find_user_by_email(email)
        if not user:
            print(f"ERROR: no Clerk user found with email {email!r}", file=sys.stderr)
            return 1
        set_role(user["id"], "tenzo_admin")
        print(f"✓ granted tenzo_admin to {user['id']} ({email})")
        print()
        print("NEXT: sign out and back in on http://localhost:3000 to refresh your session.")
        return 0

    print(f"ERROR: unknown command {cmd!r}", file=sys.stderr)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

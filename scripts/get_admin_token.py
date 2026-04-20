"""
get_admin_token.py — Request an OTP and exchange it for an admin Bearer token.

Usage:
  python scripts/get_admin_token.py
  python scripts/get_admin_token.py --email other@example.com

Saves the token to /tmp/admin_token.txt for use by other scripts.
"""

import argparse
import os
import sys

try:
    import httpx
except ImportError:
    print("httpx required: pip install httpx", file=sys.stderr)
    sys.exit(1)

SUPABASE_URL = "https://admeurikrskfpjxbvkqk.supabase.co"
ANON_KEY     = "sb_publishable_lCNu2XbpnlBCJb7H0e0kmQ_705WVrSH"
DEFAULT_EMAIL = "pablo.melanadayton+3@gmail.com"
TOKEN_PATH   = "/tmp/admin_token.txt"

HEADERS = {
    "apikey":       ANON_KEY,
    "authorization": f"Bearer {ANON_KEY}",
    "content-type": "application/json",
    "x-supabase-api-version": "2024-01-01",
}


def request_otp(email: str) -> None:
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/otp",
        headers=HEADERS,
        json={
            "email": email,
            "data": {},
            "create_user": True,
            "gotrue_meta_security": {},
            "code_challenge": None,
            "code_challenge_method": None,
        },
    )
    resp.raise_for_status()
    print(f"OTP sent to {email}")


def verify_otp(email: str, otp: str) -> str:
    resp = httpx.post(
        f"{SUPABASE_URL}/auth/v1/verify",
        headers=HEADERS,
        json={"email": email, "token": otp, "type": "email"},
    )
    resp.raise_for_status()
    token = resp.json().get("access_token")
    if not token:
        print(f"Unexpected response: {resp.text}", file=sys.stderr)
        sys.exit(1)
    return token


def main():
    p = argparse.ArgumentParser(description="Get admin Bearer token via OTP")
    p.add_argument("--email", default=DEFAULT_EMAIL)
    args = p.parse_args()

    request_otp(args.email)

    otp = input("Enter OTP code from email: ").strip()
    token = verify_otp(args.email, otp)

    with open(TOKEN_PATH, "w") as f:
        f.write(token)

    print(f"Token saved to {TOKEN_PATH}")
    print(f"\nExport for use in other commands:")
    print(f"  export ADMIN_TOKEN=$(cat {TOKEN_PATH})")


if __name__ == "__main__":
    main()

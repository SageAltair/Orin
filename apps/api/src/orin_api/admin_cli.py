"""Explicit administrator role provisioning for operators."""

import argparse
from sqlalchemy import select

from orin_api.database import SessionLocal
from orin_api.models import User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or remove Orin administrator access.")
    parser.add_argument("action", choices=("promote", "demote"))
    parser.add_argument("email")
    args = parser.parse_args()
    with SessionLocal.begin() as session:
        user = session.scalar(select(User).where(User.email == args.email.strip().casefold()))
        if user is None:
            parser.error("No user exists with that email address")
        user.is_admin = args.action == "promote"
    print(f"{args.email}: administrator access {'granted' if args.action == 'promote' else 'removed'}")


if __name__ == "__main__":
    main()

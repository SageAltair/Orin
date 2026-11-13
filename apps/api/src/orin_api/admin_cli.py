"""Explicit, attributable administrator role provisioning for operators."""

import argparse
import getpass
import os

from sqlalchemy import select

from orin_api.database import SessionLocal
from orin_api.models import AdminAuditEvent, User


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant or remove Orin administrator access.")
    parser.add_argument("action", choices=("promote", "demote"))
    parser.add_argument("email")
    parser.add_argument(
        "--operator",
        default=os.environ.get("ORIN_ADMIN_OPERATOR") or getpass.getuser(),
        help="Audited operator identity (defaults to ORIN_ADMIN_OPERATOR or the OS account).",
    )
    args = parser.parse_args()
    operator = args.operator.strip()
    if not operator or len(operator) > 120 or chr(10) in operator or chr(13) in operator:
        parser.error("Operator identity must be a non-empty single line of at most 120 characters")

    with SessionLocal.begin() as session:
        user = session.scalar(select(User).where(User.email == args.email.strip().casefold()))
        if user is None:
            parser.error("No user exists with that email address")
        previous = bool(user.is_admin)
        desired = args.action == "promote"
        user.is_admin = desired
        action = (
            "admin.role.unchanged" if previous == desired
            else "admin.role.promoted" if desired
            else "admin.role.demoted"
        )
        session.add(AdminAuditEvent(
            actor_user_id=None,
            action=action,
            target_type="user",
            target_id=str(user.id),
            detail_json={
                "operator": operator,
                "previous_is_admin": previous,
                "is_admin": desired,
            },
        ))
    print(f"{args.email}: administrator access {'granted' if args.action == 'promote' else 'removed'}")


if __name__ == "__main__":
    main()

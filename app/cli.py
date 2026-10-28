"""Command-line admin tasks.

Usage::

    python -m app.cli make-admin you@example.com
    python -m app.cli make-admin you@example.com --revoke
"""

import argparse
import sys
from typing import Optional

from sqlmodel import Session, select

from app.core.database import engine
from app.features.users.models import User


def make_admin(session: Session, email: str, revoke: bool = False) -> str:
    """Grant (or revoke) admin rights for an existing account.

    Raises:
        LookupError: no account with that e-mail address.
    """
    user = session.exec(select(User).where(User.email == email.strip())).first()
    if user is None:
        raise LookupError(f"No account with e-mail {email!r}; register it first")
    user.is_superuser = not revoke
    session.add(user)
    session.commit()
    return f"{user.email} is {'no longer' if revoke else 'now'} an admin"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    admin = commands.add_parser("make-admin", help="give an account admin rights")
    admin.add_argument("email")
    admin.add_argument("--revoke", action="store_true", help="remove admin rights")
    args = parser.parse_args(argv)

    with Session(engine) as session:
        try:
            print(make_admin(session, args.email, args.revoke))
        except LookupError as e:
            print(e, file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

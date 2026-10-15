"""
Manage the dashboard's user accounts. People sign in with their MINEDUC GIS portal account; their account here is
added at their first sign-in (as an administrator). From the command line you change what they may do here:

  python -m app.users role jdoe viewer       admin or viewer
  python -m app.users disable jdoe           can no longer sign in here, even with a valid portal password
  python -m app.users enable jdoe
  python -m app.users list

Run from backend/ (or in the API container: docker compose ... exec api python -m app.users ...).
"""
from __future__ import annotations

import argparse
import sys

from sqlalchemy import delete, select

from . import models as M
from .db import SessionLocal
from .services.auth import find_user


def _user(session, username: str) -> M.User:
    user = find_user(session, username)
    if user is None:
        sys.exit(f"No user {username} (people appear here after their first sign-in).")
    return user


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.users", description="Manage dashboard user accounts.")
    sub = parser.add_subparsers(dest="command", required=True)
    role = sub.add_parser("role", help="make an account an administrator or a viewer")
    role.add_argument("username")
    role.add_argument("role", choices=["admin", "viewer"])
    for name, text in (("disable", "block sign-in"), ("enable", "allow sign-in")):
        sub.add_parser(name, help=text).add_argument("username")
    sub.add_parser("list", help="list the accounts")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        if args.command in ("disable", "enable"):
            user = _user(session, args.username)
            user.is_active = args.command == "enable"
            if not user.is_active:
                session.execute(delete(M.UserSession).where(M.UserSession.user_id == user.id))
            print(f"{user.username} {args.command}d.")
        elif args.command == "role":
            user = _user(session, args.username)
            user.role = args.role
            print(f"{user.username} is now {'an administrator' if args.role == 'admin' else 'a viewer'}.")
        else:
            users = session.scalars(select(M.User).order_by(M.User.username)).all()
            for u in users:
                last = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "never"
                print(f"{u.username:30} {u.full_name or '':30} {u.role:7} {'active' if u.is_active else 'disabled':9} last sign-in {last}")
            print(f"{len(users)} account(s).")
        session.commit()


if __name__ == "__main__":
    main()

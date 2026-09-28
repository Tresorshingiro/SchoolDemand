"""
Manage the dashboard's user accounts (there is no sign-up page: an administrator creates the accounts).

  python -m app.users create jane@mineduc.gov.rw --name "Jane Doe"     asks for the password
  python -m app.users password jane@mineduc.gov.rw                     new password (signs the user out everywhere)
  python -m app.users disable jane@mineduc.gov.rw                      can no longer sign in (enable: undo)
  python -m app.users enable jane@mineduc.gov.rw
  python -m app.users list

Run from backend/ (or in the API container: docker compose ... exec api python -m app.users ...).
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import delete, select

from . import models as M
from .db import SessionLocal
from .services.auth import hash_password, normalize_email


def _ask_password() -> str:
    while True:
        first = getpass.getpass("Password: ")
        if first != getpass.getpass("Repeat the password: "):
            print("The two passwords differ, try again.")
            continue
        try:
            return hash_password(first)
        except ValueError as e:
            print(e)


def _user(session, email: str) -> M.User:
    user = session.scalar(select(M.User).where(M.User.email == normalize_email(email)))
    if user is None:
        sys.exit(f"No user {email}.")
    return user


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.users", description="Manage dashboard user accounts.")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create an account")
    create.add_argument("email")
    create.add_argument("--name", help="full name shown in the dashboard")
    for name, text in (("password", "set a new password"), ("disable", "block sign-in"), ("enable", "allow sign-in")):
        sub.add_parser(name, help=text).add_argument("email")
    sub.add_parser("list", help="list the accounts")
    args = parser.parse_args(argv)

    with SessionLocal() as session:
        if args.command == "create":
            email = normalize_email(args.email)
            if "@" not in email:
                sys.exit("That is not an email address.")
            if session.scalar(select(M.User.id).where(M.User.email == email)):
                sys.exit(f"{email} already has an account (change its password with: python -m app.users password {email}).")
            session.add(M.User(email=email, full_name=args.name, password_hash=_ask_password(), is_active=True))
            print(f"Created {email}.")
        elif args.command == "password":
            user = _user(session, args.email)
            user.password_hash = _ask_password()
            session.execute(delete(M.UserSession).where(M.UserSession.user_id == user.id))
            print(f"Password changed for {user.email}; signed out everywhere.")
        elif args.command in ("disable", "enable"):
            user = _user(session, args.email)
            user.is_active = args.command == "enable"
            if not user.is_active:
                session.execute(delete(M.UserSession).where(M.UserSession.user_id == user.id))
            print(f"{user.email} {args.command}d.")
        else:
            users = session.scalars(select(M.User).order_by(M.User.email)).all()
            for u in users:
                last = u.last_login_at.strftime("%Y-%m-%d %H:%M") if u.last_login_at else "never"
                print(f"{u.email:40} {u.full_name or '':30} {'active' if u.is_active else 'disabled':9} last sign-in {last}")
            print(f"{len(users)} account(s).")
        session.commit()


if __name__ == "__main__":
    main()

"""Sign in, sign out, who is signed in (session cookie, see services/auth.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..schemas import LoginIn, UserOut
from ..services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut, summary="Sign in with email and password (sets the session cookie)")
def login(body: LoginIn, request: Request, response: Response, session: Session = Depends(get_session)):
    user = auth.authenticate(session, body.email, body.password)
    token, max_age = auth.start_session(session, user, body.remember)
    auth.set_cookie(request, response, token, max_age)
    return user


@router.post("/logout", status_code=204, summary="Sign out (ends the session)")
def logout(request: Request, session: Session = Depends(get_session)) -> Response:
    auth.end_session(session, request.cookies.get(auth.COOKIE))
    response = Response(status_code=204)
    auth.clear_cookie(response)
    return response


@router.get("/me", response_model=UserOut, summary="The signed-in user (401 when not signed in)")
def me(user: M.User = Depends(auth.current_user)):
    return user

"""Sign in, sign out, who is signed in, change your password (session cookie, see services/auth.py)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .. import models as M
from ..db import get_session
from ..schemas import LoginIn, PasswordChangeIn, UserOut
from ..services import auth
from ..services.audit import audit

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
def me(user: M.User = Depends(auth.signed_in_user)):
    return user


@router.post("/password", status_code=204, summary="Change your own password (signs your other browsers out)")
def change_password(body: PasswordChangeIn, request: Request, session: Session = Depends(get_session),
                    user: M.User = Depends(auth.signed_in_user)) -> Response:
    if not auth.verify_password(user.password_hash, body.current_password):
        raise HTTPException(400, "The current password is wrong.")
    if body.new_password == body.current_password:
        raise HTTPException(400, "The new password must differ from the current one.")
    try:
        user.password_hash = auth.hash_password(body.new_password)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    user.must_change_password = False
    auth.end_user_sessions(session, user.id, keep_token=request.cookies.get(auth.COOKIE))
    audit(session, user, "user.password_change", user.email)
    session.commit()
    return Response(status_code=204)

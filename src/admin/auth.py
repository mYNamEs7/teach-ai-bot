import secrets
from typing import Optional

from fastapi import Request, HTTPException
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware

from src.config import settings

ADMIN_SESSION_KEY = "admin_authenticated"


def verify_admin_password(password: str) -> bool:
    return password == settings.admin_password if hasattr(settings, "admin_password") else False


def is_authenticated(request: Request) -> bool:
    return request.session.get(ADMIN_SESSION_KEY, False)


def set_authenticated(request: Request) -> None:
    request.session[ADMIN_SESSION_KEY] = True


def logout_admin(request: Request) -> None:
    request.session[ADMIN_SESSION_KEY] = False

# OAuth2 configuration
import json
import os

import httpx
import pydantic
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import RedirectResponse

load_dotenv()

keycloak_url = os.environ.get("KEYCLOAK_URL")
client_id = os.environ.get("CLIENT_ID")
client_secret = os.environ.get("CLIENT_SECRET")
redirect_uri = os.environ.get("REDIRECT_URI")

if not all([keycloak_url, client_id, client_secret, redirect_uri]):
    raise ValueError("Missing required environment variables for OAuth2 configuration")


class ShinyCredentialsMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        request = HTTPConnection(scope, receive)
        if "access_token" in request.session:
            user = await get_user_info(request)
            if user:
                shiny_credentials = {"user": user.name, "groups": []}
                headers = dict(scope["headers"])
                headers[b"shiny-server-credentials"] = json.dumps(
                    shiny_credentials
                ).encode()
                scope["headers"] = [(k, v) for k, v in headers.items()]
        await self.app(scope, receive, send)


class EnsureAuthenticatedMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if "access_token" not in request.session:
            auth_url = (
                f"{keycloak_url}/protocol/openid-connect/auth"
                f"?client_id={client_id}"
                f"&redirect_uri={redirect_uri}"
                f"&response_type=code"
                f"&scope=openid profile email roles groups"
            )
            return RedirectResponse(auth_url)

        response = await call_next(request)
        return response


class UserInfo(pydantic.BaseModel):
    sub: str
    email_verified: bool
    name: str
    preferred_username: str
    given_name: str
    family_name: str
    email: str


async def get_user_info(request: Request) -> UserInfo | None:
    token = get_token_from_storage(request)
    if not token:
        return None

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{keycloak_url}/protocol/openid-connect/userinfo",
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            clear_token_from_storage(request)
            return None

        user_info = resp.json()
        print(user_info)
        return UserInfo(**user_info)


def get_token_from_storage(request: Request):
    return request.session.get("access_token")


def save_token_to_storage(request: Request, token: str):
    request.session["access_token"] = token


def clear_token_from_storage(request: Request):
    request.session.pop("access_token", None)


async def exchange_code(code: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{keycloak_url}/protocol/openid-connect/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token")


def logout(request: Request):
    clear_token_from_storage(request)
    url = f"{keycloak_url}/protocol/openid-connect/logout?client_id={client_id}&redirect_uri={redirect_uri}"
    return RedirectResponse(url=url)

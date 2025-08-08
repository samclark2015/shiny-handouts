# OAuth2 configuration
import json
import os
from typing import Optional

import httpx
import pydantic
from dotenv import load_dotenv
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.responses import RedirectResponse

load_dotenv()

oauth_url = os.environ.get("OAUTH_URL")
oauth_client_id = os.environ.get("OAUTH_CLIENT_ID")
oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")
oauth_redirect_uri = os.environ.get("OAUTH_REDIRECT_URI")

if not all([oauth_url, oauth_client_id, oauth_client_secret, oauth_redirect_uri]):
    raise ValueError("Missing required environment variables for OAuth2 configuration")


class OpenIDConfiguration(pydantic.BaseModel):
    authorization_endpoint: str
    token_endpoint: str
    userinfo_endpoint: str
    end_session_endpoint: str


_openid_config: Optional[OpenIDConfiguration] = None


async def get_openid_configuration() -> OpenIDConfiguration:
    global _openid_config
    if _openid_config is not None:
        return _openid_config

    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{oauth_url}/.well-known/openid-configuration")
        if resp.status_code != 200:
            raise ValueError(
                f"Failed to fetch OpenID configuration: {resp.status_code}"
            )

        config_data = resp.json()
        _openid_config = OpenIDConfiguration(**config_data)
        return _openid_config


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
            config = await get_openid_configuration()
            auth_url = (
                f"{config.authorization_endpoint}"
                f"?client_id={oauth_client_id}"
                f"&redirect_uri={oauth_redirect_uri}"
                f"&response_type=code"
                f"&scope=openid profile email roles groups"
            )
            return RedirectResponse(auth_url)

        response = await call_next(request)
        return response


class UserInfo(pydantic.BaseModel):
    sub: str
    name: str
    email: str


async def get_user_info(request: HTTPConnection) -> UserInfo | None:
    token = get_token_from_storage(request)
    if not token:
        return None

    config = await get_openid_configuration()
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            config.userinfo_endpoint,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code != 200:
            clear_token_from_storage(request)
            return None

        user_info = resp.json()
        print(user_info)
        return UserInfo(**user_info)


def get_token_from_storage(request: HTTPConnection):
    return request.session.get("access_token")


def save_token_to_storage(request: HTTPConnection, token: str):
    request.session["access_token"] = token


def clear_token_from_storage(request: HTTPConnection):
    request.session.pop("access_token", None)


async def exchange_code(code: str):
    config = await get_openid_configuration()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            config.token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": oauth_redirect_uri,
                "client_id": oauth_client_id,
                "client_secret": oauth_client_secret,
            },
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return data.get("access_token")


async def logout(request: HTTPConnection):
    clear_token_from_storage(request)
    config = await get_openid_configuration()
    url = f"{config.end_session_endpoint}?client_id={oauth_client_id}&redirect_uri={oauth_redirect_uri}"
    return RedirectResponse(url=url)

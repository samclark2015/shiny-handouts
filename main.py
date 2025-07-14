import os
from pathlib import Path

from dotenv import load_dotenv
from shiny.express import wrap_express_app
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route

from auth import (
    EnsureAuthenticatedMiddleware,
    ShinyCredentialsMiddleware,
    exchange_code,
    logout,
    save_token_to_storage,
)

load_dotenv()

app_middleware = [
    Middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET"]),
]

if "AUTH_ENABLED" in os.environ:
	app_middleware.append(
		 Middleware(ShinyCredentialsMiddleware)
	)

shiny_middleware = [Middleware(EnsureAuthenticatedMiddleware)]

shiny_app = wrap_express_app(Path("app.py"))


async def auth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        return PlainTextResponse("No code provided", status_code=400)

    token = await exchange_code(code)
    if not token:
        return PlainTextResponse("Failed to exchange code for token", status_code=400)
    save_token_to_storage(request, token)
    return RedirectResponse(url="/")


def auth_logout(request: Request):
    return logout(request)


routes = [
    Route("/callback", endpoint=auth_callback),
    Route("/logout", endpoint=auth_logout),
    Mount("/", app=shiny_app, name="shiny", middleware=shiny_middleware),
]

app = Starlette(debug=True, routes=routes, middleware=app_middleware)

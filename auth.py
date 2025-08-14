import os

from authlib.integrations.starlette_client import OAuth, OAuthError
from fastapi import Request
from fastapi.responses import RedirectResponse
from nicegui import app, ui
from starlette.middleware.base import BaseHTTPMiddleware

oauth_url = os.environ.get("OAUTH_URL")
oauth_client_id = os.environ.get("OAUTH_CLIENT_ID")
oauth_client_secret = os.environ.get("OAUTH_CLIENT_SECRET")


oauth = OAuth()

unrestricted_page_routes = {"/callback", "/login", "/login/start"}


class AuthMiddleware(BaseHTTPMiddleware):
    """This middleware restricts access to all NiceGUI pages.

    It redirects the user to the login page if they are not authenticated.
    """

    async def dispatch(self, request: Request, call_next):
        user_data = app.storage.user.get("user_data", None)
        if not user_data:
            if (
                not request.url.path.startswith("/_nicegui")
                and request.url.path not in unrestricted_page_routes
            ):
                url = request.url_for("login")
                return RedirectResponse(url)
        return await call_next(request)


def enable_oauth():
    print("Enabling OAuth")
    oauth.register(
        "authentik",
        client_id=oauth_client_id,
        client_secret=oauth_client_secret,
        server_metadata_url=oauth_url,
        client_kwargs={"scope": "openid email profile"},
    )

    @app.get("/callback")
    async def oauth_handler(request: Request):
        try:
            user_data = await oauth.authentik.authorize_access_token(request)
        except OAuthError as e:
            print(f"OAuth error: {e}")
            return "OAuth Failure."

        app.storage.user["user_data"] = user_data
        return RedirectResponse("/")

    app.add_middleware(AuthMiddleware)

    @ui.page("/login")
    async def login():
        with ui.column().classes("w-full h-dvh justify-center items-center"):
            with ui.card(align_items="center").classes("w-1/4 p-12"):
                ui.label("Login").classes("text-2xl font-bold")
                ui.label(
                    "Welcome to Shiny Handouts! This site allows you to access and manage handouts securely. You must log in to use the site."
                ).classes("mb-4")
                ui.button(
                    "Login with Authentik",
                    on_click=lambda: ui.navigate.to("/login/start"),
                )

    @app.get("/login/start")
    async def login_start(request: Request):
        url = request.url_for("oauth_handler")
        return await oauth.authentik.authorize_redirect(request, url)


def logout() -> None:
    del app.storage.user["user_data"]
    ui.navigate.to("/")

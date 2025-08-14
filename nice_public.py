import os

from dotenv import load_dotenv
from nicegui import app, ui

from auth import enable_oauth
from pages import register_pages
from startup import initialize

load_dotenv()


if "AUTH_ENABLED" in os.environ:
    enable_oauth()

app.on_startup(initialize)

register_pages()

secret = os.environ.get("SESSION_SECRET")
ui.run(
    host="0.0.0.0",
    port=8080,
    proxy_headers=True,
    storage_secret=secret,
    reload=False,
    show=False,
    uvicorn_logging_level="info",
    forwarded_allow_ips="*",
)

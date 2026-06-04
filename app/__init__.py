"""
FastAPI routers package.

`main.py` uses `from app import notification_app` — each submodule is loaded on
demand; do not import routers here (importing `app.logging_config` would
otherwise pull in `core.database` before `load_dotenv()` in `main.py`).
"""

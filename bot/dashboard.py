from html import escape
from typing import Optional

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from .config import Settings
from .database import session_scope
from .models import GroupPrivacyMode, GroupSetting
from .services.leaderboard import get_leaderboard


def start_dashboard_server(settings: Settings):
    """Start the dashboard server (synchronous for multiprocessing)."""
    try:
        # Create dashboard app directly
        # Note: This is a simplified version for multiprocessing compatibility
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("/")
        async def root():
            return {"message": "Ingress Leaderboard Dashboard - Running in simplified mode"}

        @app.get("/health")
        async def health():
            return {"status": "healthy"}

        return app, None
    except Exception as e:
        print(f"❌ Failed to start dashboard server: {e}")
        return None, None


def run_dashboard_server_sync(app, settings: Settings):
    """Run the dashboard server synchronously."""
    import uvicorn

    try:
        print(f"🌐 Dashboard server starting on http://{settings.dashboard_host}:{settings.dashboard_port}")
        uvicorn.run(
            app,
            host=settings.dashboard_host,
            port=settings.dashboard_port,
            log_level="warning"  # Reduce log noise
        )
    except Exception as e:
        print(f"❌ Dashboard server error: {e}")


async def start_full_dashboard_server(settings: Settings, session_factory):
    """Start the full dashboard server with all features (for non-multiprocessing use)."""
    app = create_dashboard_app(settings, session_factory)
    return app, None


def create_dashboard_app(settings: Settings, session_factory: async_sessionmaker) -> FastAPI:
    app = FastAPI()

    def ensure_admin(token: Optional[str]) -> None:
        expected = settings.dashboard_admin_token
        if expected and token != expected:
            raise HTTPException(status_code=401, detail="unauthorized")

    @app.get("/", response_class=HTMLResponse)
    async def leaderboard_view(chat_id: Optional[int] = None, limit: Optional[int] = None) -> HTMLResponse:
        effective_limit = limit if limit is not None and limit > 0 else settings.leaderboard_size
        async with session_scope(session_factory) as session:
            rows = await get_leaderboard(session, effective_limit, chat_id)
        table_rows = "".join(
            f"<tr><td>{index}</td><td>{escape(codename)}</td><td>{escape(faction)}</td><td>{total_ap:,}</td></tr>"
            for index, (codename, faction, total_ap) in enumerate(rows, start=1)
        )
        if not table_rows:
            table_rows = "<tr><td colspan='4'>No submissions</td></tr>"
        chat_value = "" if chat_id is None else str(chat_id)
        limit_value = str(effective_limit)
        html = (
            "<html><head><title>Ingress Leaderboard</title></head><body>"
            "<h1>Ingress Leaderboard</h1>"
            "<form method='get'>"
            f"<label>Chat ID <input type='number' name='chat_id' value='{escape(chat_value)}'></label>"
            f"<label>Limit <input type='number' min='1' name='limit' value='{escape(limit_value)}'></label>"
            "<button type='submit'>Refresh</button>"
            "</form>"
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<thead><tr><th>#</th><th>Agent</th><th>Faction</th><th>Total AP</th></tr></thead>"
            f"<tbody>{table_rows}</tbody>"
            "</table>"
            "</body></html>"
        )
        return HTMLResponse(html)

    @app.get("/admin", response_class=HTMLResponse)
    async def admin_page(token: Optional[str] = None) -> HTMLResponse:
        ensure_admin(token)
        async with session_scope(session_factory) as session:
            result = await session.execute(select(GroupSetting).order_by(GroupSetting.chat_id))
            group_settings = list(result.scalars())
        checked = " checked" if settings.autodelete_enabled else ""
        token_value = "" if token is None else escape(token)
        group_rows = "".join(
            f"<tr><td>{setting.chat_id}</td><td>{escape(setting.privacy_mode)}</td><td>{setting.updated_at.isoformat()}</td></tr>"
            for setting in group_settings
        )
        if not group_rows:
            group_rows = "<tr><td colspan='3'>No group settings</td></tr>"
        html = (
            "<html><head><title>Administration</title></head><body>"
            "<h1>Administration</h1>"
            "<section>"
            "<h2>Autodelete Settings</h2>"
            "<form method='post' action='/admin/autodelete'>"
            f"<input type='hidden' name='token' value='{token_value}'>"
            f"<label>Delay (seconds) <input type='number' min='0' name='delay_seconds' value='{settings.autodelete_delay_seconds}'></label>"
            f"<label><input type='checkbox' name='enabled' value='on'{checked}> Enabled</label>"
            "<button type='submit'>Save</button>"
            "</form>"
            "</section>"
            "<section>"
            "<h2>Group Privacy Mode</h2>"
            "<form method='post' action='/admin/group_privacy'>"
            f"<input type='hidden' name='token' value='{token_value}'>"
            "<label>Chat ID <input type='number' name='chat_id' required></label>"
            "<label>Mode <select name='mode'>"
            + "".join(
                f"<option value='{option.value}'>{option.value}</option>"
                for option in GroupPrivacyMode
            )
            + "</select></label>"
            "<button type='submit'>Save</button>"
            "</form>"
            "<table border='1' cellpadding='6' cellspacing='0'>"
            "<thead><tr><th>Chat ID</th><th>Mode</th><th>Updated</th></tr></thead>"
            f"<tbody>{group_rows}</tbody>"
            "</table>"
            "</section>"
            "</body></html>"
        )
        return HTMLResponse(html)

    @app.post("/admin/autodelete")
    async def update_autodelete(
        token: Optional[str] = Form(None),
        delay_seconds: int = Form(...),
        enabled: Optional[str] = Form(None),
    ) -> RedirectResponse:
        ensure_admin(token)
        if delay_seconds < 0:
            raise HTTPException(status_code=400, detail="invalid delay")
        settings.autodelete_delay_seconds = delay_seconds
        settings.autodelete_enabled = enabled == "on"
        redirect_token = "" if token is None else token
        return RedirectResponse(url=f"/admin?token={redirect_token}", status_code=303)

    @app.post("/admin/group_privacy")
    async def update_group_privacy(
        token: Optional[str] = Form(None),
        chat_id: int = Form(...),
        mode: str = Form(...),
    ) -> RedirectResponse:
        ensure_admin(token)
        if chat_id == 0:
            raise HTTPException(status_code=400, detail="invalid chat id")
        try:
            privacy = GroupPrivacyMode(mode)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid mode")
        async with session_scope(session_factory) as session:
            result = await session.execute(select(GroupSetting).where(GroupSetting.chat_id == chat_id))
            setting = result.scalar_one_or_none()
            if setting is None:
                session.add(GroupSetting(chat_id=chat_id, privacy_mode=privacy.value))
            else:
                setting.privacy_mode = privacy.value
        redirect_token = "" if token is None else token
        return RedirectResponse(url=f"/admin?token={redirect_token}", status_code=303)

    return app

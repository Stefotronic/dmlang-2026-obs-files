"""FastAPI-App: JSON-API, OBS-Overlay und Regie-Seite."""
from __future__ import annotations

import asyncio
import contextlib
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import views
from .mop import MopState
from .poller import MeosPoller

STATIC = Path(__file__).parent / "static"


class DisplayConfig(BaseModel):
    mode: str = "auto"  # "auto" (Rotation) | "fixed" (feste Klasse)
    fixed_class: int | None = None
    rotate_classes: list[int] = []  # leer = alle aktiven Klassen
    page_seconds: int = 15
    show_ticker: bool = True
    ticker_count: int = 10
    hide_empty: bool = True
    skip_counter: int = 0


class DisplayUpdate(BaseModel):
    mode: str | None = None
    fixed_class: int | None = None
    rotate_classes: list[int] | None = None
    page_seconds: int | None = None
    show_ticker: bool | None = None
    ticker_count: int | None = None
    hide_empty: bool | None = None


class CurrentView(BaseModel):
    class_id: int | None = None
    class_name: str = ""
    page: int = 0
    pages: int = 0


def create_app(meos_url: str, poll_interval: float = 2.0, demo: bool = False, demo_speed: float = 10.0) -> FastAPI:
    state = MopState()
    poller = MeosPoller(state, meos_url, interval=poll_interval)
    display = DisplayConfig()
    current: dict = {"view": CurrentView().model_dump(), "at": None}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        task = asyncio.create_task(poller.run())
        try:
            yield
        finally:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="MeOS → OBS", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    if demo:
        from .mock_meos import MockMeosServer, Simulation

        app.include_router(MockMeosServer(Simulation(speed=demo_speed)).router(), prefix="/mock")

    @app.get("/", include_in_schema=False)
    async def index():
        return RedirectResponse("/control")

    @app.get("/overlay", include_in_schema=False)
    async def overlay():
        return FileResponse(STATIC / "overlay.html")

    @app.get("/control", include_in_schema=False)
    async def control():
        return FileResponse(STATIC / "control.html")

    @app.get("/api/status")
    async def api_status():
        return {
            "meos": poller.status(),
            "competition": state.competition,
            "version": state.version,
            "counts": {
                "classes": len(state.classes),
                "competitors": len(state.competitors),
                "teams": len(state.teams),
            },
            "server_time": time.time(),
        }

    @app.get("/api/classes")
    async def api_classes():
        return views.classes_list(state)

    @app.get("/api/class/{cls_id}")
    async def api_class(cls_id: int):
        res = views.class_results(state, cls_id)
        if res is None:
            raise HTTPException(404, "Klasse nicht gefunden")
        return res

    @app.get("/api/ticker")
    async def api_ticker(limit: int = 12):
        return views.ticker(state, max(1, min(limit, 50)))

    @app.get("/api/display")
    async def get_display():
        return {"config": display.model_dump(), "current": current}

    @app.post("/api/display")
    async def set_display(update: DisplayUpdate):
        nonlocal display
        data = update.model_dump(exclude_unset=True)
        if "mode" in data and data["mode"] not in ("auto", "fixed"):
            raise HTTPException(400, "mode muss 'auto' oder 'fixed' sein")
        if "page_seconds" in data:
            data["page_seconds"] = max(3, min(int(data["page_seconds"]), 300))
        if "ticker_count" in data:
            data["ticker_count"] = max(1, min(int(data["ticker_count"]), 30))
        display = display.model_copy(update=data)
        return display.model_dump()

    @app.post("/api/display/skip")
    async def skip():
        display.skip_counter += 1
        return display.model_dump()

    @app.post("/api/display/current")
    async def set_current(view: CurrentView):
        current["view"] = view.model_dump()
        current["at"] = time.time()
        return {"ok": True}

    return app

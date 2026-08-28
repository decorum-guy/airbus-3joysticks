from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .runtime import ROLES, Runtime


STATIC_DIR = Path(__file__).with_name("static")


def create_app(runtime: Runtime) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="Airbus 3 Joysticks", version="0.1.0", lifespan=lifespan)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/editor")
    async def editor() -> FileResponse:
        return FileResponse(STATIC_DIR / "editor.html")

    @app.get("/haptics")
    async def haptics_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "haptics.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "simconnect": runtime.bridge.state()}

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return runtime.public_state()

    @app.post("/api/assign/cancel")
    async def cancel_assignment() -> dict[str, Any]:
        runtime.cancel_assignment()
        return {"ok": True}

    @app.post("/api/assign/{role}")
    async def assign(role: str) -> dict[str, Any]:
        if role not in ROLES:
            raise HTTPException(status_code=404, detail="Unknown role")
        runtime.arm_assignment(role)
        return {"ok": True, "assignment_target": role}

    @app.delete("/api/assign/{role}")
    async def clear_assignment(role: str) -> dict[str, Any]:
        if role not in ROLES:
            raise HTTPException(status_code=404, detail="Unknown role")
        runtime.clear_assignment(role)
        return {"ok": True}

    @app.put("/api/bindings/{role}")
    async def replace_bindings(role: str, bindings: list[dict[str, Any]] = Body(...)) -> dict[str, Any]:
        if role not in ROLES:
            raise HTTPException(status_code=404, detail="Unknown role")
        try:
            runtime.replace_bindings(role, bindings)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, "bindings": bindings}

    @app.put("/api/haptics")
    async def update_haptics(haptics: dict[str, Any] = Body(...)) -> dict[str, Any]:
        try:
            result = runtime.update_haptics(haptics)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"ok": True, **result}

    @app.post("/api/haptics/test/{kind}")
    async def test_haptics(kind: str, payload: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        role = payload.get("role") if isinstance(payload, dict) else None
        try:
            result = runtime.test_haptic(kind, role=role)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"ok": True, "test": result}

    @app.websocket("/ws")
    async def websocket_state(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(runtime.public_state())
                await asyncio.sleep(0.25)
        except (WebSocketDisconnect, RuntimeError):
            return

    return app

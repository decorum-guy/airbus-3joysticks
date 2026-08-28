from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse

from .rotary_settings import CONTROL_ROUTES, RotarySensitivityStore
from .runtime import ROLES, ROTARY_PRECISION_SCALES, Runtime


STATIC_DIR = Path(__file__).with_name("static")


def create_app(runtime: Runtime) -> FastAPI:
    rotary_sensitivity = RotarySensitivityStore()

    def apply_rotary_sensitivity(snapshot: dict[str, Any]) -> None:
        values = snapshot["values"]
        for control, route in CONTROL_ROUTES.items():
            precision = float(values[control])
            ROTARY_PRECISION_SCALES[route] = (precision, precision)
        # Avoid carrying partial angular accumulation across a live tuning change.
        runtime.rotary.reset()

    apply_rotary_sensitivity(rotary_sensitivity.snapshot())

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await runtime.start()
        try:
            yield
        finally:
            await runtime.stop()

    app = FastAPI(title="Airbus 3 Joysticks", version="0.3.0", lifespan=lifespan)

    @app.get("/")
    async def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        html = html.replace(
            "</head>",
            '<link rel="stylesheet" href="/rotary-controls.css" /></head>',
        )
        html = html.replace(
            "</body>",
            '<script src="/rotary-controls.js"></script></body>',
        )
        return HTMLResponse(html)

    @app.get("/rotary-controls.css")
    async def rotary_controls_css() -> FileResponse:
        return FileResponse(STATIC_DIR / "rotary-controls.css", media_type="text/css")

    @app.get("/rotary-controls.js")
    async def rotary_controls_js() -> FileResponse:
        return FileResponse(STATIC_DIR / "rotary-controls.js", media_type="text/javascript")

    @app.get("/editor")
    async def editor() -> FileResponse:
        return FileResponse(STATIC_DIR / "editor.html")

    @app.get("/haptics")
    async def haptics_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "haptics.html")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        state = runtime.public_state()
        return {
            "ok": True,
            "ready": state["readiness"]["ready"],
            "readiness": state["readiness"],
            "simconnect": state["simconnect"],
        }

    @app.get("/api/state")
    async def state() -> dict[str, Any]:
        return runtime.public_state()

    @app.get("/api/preflight")
    async def preflight() -> dict[str, Any]:
        state = runtime.public_state()
        return {
            "ready": state["readiness"]["ready"],
            "readiness": state["readiness"],
            "roles": {
                key: {
                    "enabled": role["enabled"],
                    "online": role["online"],
                    "device": role["runtime_device"],
                }
                for key, role in state["roles"].items()
            },
            "simconnect": state["simconnect"],
        }

    @app.get("/api/rotary-sensitivity")
    async def get_rotary_sensitivity() -> dict[str, Any]:
        return rotary_sensitivity.snapshot()

    @app.put("/api/rotary-sensitivity/{control}")
    async def update_rotary_sensitivity(
        control: str,
        payload: dict[str, Any] = Body(...),
    ) -> dict[str, Any]:
        if "precision" not in payload:
            raise HTTPException(status_code=400, detail="precision is required")
        try:
            snapshot = rotary_sensitivity.set(control, payload["precision"])
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown rotary control") from exc
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        apply_rotary_sensitivity(snapshot)
        return {"ok": True, "sensitivity": snapshot}

    @app.post("/api/rotary-sensitivity/{control}/reset")
    async def reset_rotary_sensitivity(control: str) -> dict[str, Any]:
        try:
            snapshot = rotary_sensitivity.reset(control)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Unknown rotary control") from exc
        apply_rotary_sensitivity(snapshot)
        return {"ok": True, "sensitivity": snapshot}

    @app.post("/api/rotary-sensitivity/reset")
    async def reset_all_rotary_sensitivity() -> dict[str, Any]:
        snapshot = rotary_sensitivity.reset()
        apply_rotary_sensitivity(snapshot)
        return {"ok": True, "sensitivity": snapshot}

    @app.post("/api/assign/cancel")
    async def cancel_assignment() -> dict[str, Any]:
        runtime.cancel_assignment()
        return {"ok": True}

    @app.post("/api/assign/{role}")
    async def assign(role: str) -> dict[str, Any]:
        if role not in ROLES:
            raise HTTPException(status_code=404, detail="Unknown role")
        runtime.arm_assignment(role)
        return {"ok": True, "assignment_target": runtime.assignment_target}

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

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
from typing import Any


log = logging.getLogger(__name__)


TELEMETRY_DEFINITIONS: dict[str, tuple[str, str | None]] = {
    "aircraft_title": ("TITLE", None),
    "speed": ("AUTOPILOT AIRSPEED HOLD VAR", "Knots"),
    "heading": ("AUTOPILOT HEADING LOCK DIR", "Degrees"),
    "altitude": ("AUTOPILOT ALTITUDE LOCK VAR", "Feet"),
    "vertical_speed": ("AUTOPILOT VERTICAL HOLD VAR", "Feet per minute"),
}


@dataclass
class BridgeState:
    connected: bool = False
    last_error: str | None = None
    sent_events: int = 0
    dropped_events: int = 0
    telemetry: dict[str, Any] = field(default_factory=dict)
    telemetry_errors: dict[str, str] = field(default_factory=dict)
    last_telemetry_at: float | None = None


class SimConnectBridge:
    """Own the SimConnect handle on one background thread.

    Inputs are intentionally dropped while disconnected instead of queued for
    later replay. Replaying stale altitude/heading knob turns after the sim
    reconnects would be unsafe and surprising.

    The same worker also reads a small, fixed FCU telemetry set. Keeping reads
    and writes on one SimConnect-owning thread avoids cross-thread handle use.
    """

    def __init__(self, reconnect_seconds: float = 2.0, telemetry_seconds: float = 0.8) -> None:
        self.reconnect_seconds = float(reconnect_seconds)
        self.telemetry_seconds = max(0.25, float(telemetry_seconds))
        self._queue: Queue[dict[str, Any]] = Queue(maxsize=256)
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._state = BridgeState()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = Thread(target=self._worker, name="simconnect", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "connected": self._state.connected,
                "last_error": self._state.last_error,
                "sent_events": self._state.sent_events,
                "dropped_events": self._state.dropped_events,
                "telemetry": dict(self._state.telemetry),
                "telemetry_errors": dict(self._state.telemetry_errors),
                "last_telemetry_at": self._state.last_telemetry_at,
            }

    def _set_connected(self, connected: bool, error: str | None = None) -> None:
        with self._lock:
            self._state.connected = connected
            self._state.last_error = error
            if not connected:
                self._state.last_telemetry_at = None

    def send_event(self, event: str, data: int | None = None) -> bool:
        if not event:
            return False
        with self._lock:
            connected = self._state.connected
            if not connected:
                self._state.dropped_events += 1
                return False
        try:
            self._queue.put_nowait({"event": event, "data": data})
            return True
        except Exception:
            with self._lock:
                self._state.dropped_events += 1
            return False

    def _close(self, sc: Any) -> None:
        if sc is None:
            return
        try:
            sc.Close()
        except Exception:
            pass

    def _read_simdatum(self, sc: Any, name: str, units: str | None) -> Any:
        value = sc.get_simdatum(name, units=units, timeout_seconds=0.75)
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _refresh_telemetry(self, sc: Any) -> None:
        values: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for key, (name, units) in TELEMETRY_DEFINITIONS.items():
            try:
                values[key] = self._read_simdatum(sc, name, units)
            except Exception as exc:
                errors[key] = str(exc)
        with self._lock:
            # Keep the last known-good value for an individual datum if one
            # transient read fails; expose the error separately to the UI.
            self._state.telemetry.update(values)
            self._state.telemetry_errors = errors
            self._state.last_telemetry_at = time.time()

    def _worker(self) -> None:
        if os.name != "nt":
            self._set_connected(False, "SimConnect bridge requires Windows")
            return

        try:
            from simconnect import SimConnect
        except Exception as exc:
            self._set_connected(False, f"pysimconnect import failed: {exc}")
            return

        sc = None
        next_telemetry = 0.0
        while not self._stop.is_set():
            if sc is None:
                try:
                    sc = SimConnect(name="Airbus3Joysticks")
                    self._set_connected(True, None)
                    next_telemetry = 0.0
                    log.info("Connected to MSFS via SimConnect")
                except Exception as exc:
                    self._set_connected(False, str(exc))
                    self._stop.wait(self.reconnect_seconds)
                    continue

            now = time.monotonic()
            if now >= next_telemetry:
                try:
                    self._refresh_telemetry(sc)
                except Exception as exc:
                    # A telemetry read failure should not make control input
                    # unusable. Individual datum failures are already recorded.
                    log.debug("SimConnect telemetry refresh failed: %s", exc)
                next_telemetry = time.monotonic() + self.telemetry_seconds

            try:
                item = self._queue.get(timeout=0.05)
            except Empty:
                continue

            try:
                data = 0 if item["data"] is None else int(item["data"])
                sc.send_event(item["event"], data=data)
                with self._lock:
                    self._state.sent_events += 1
            except Exception as exc:
                log.warning("SimConnect send failed: %s", exc)
                with self._lock:
                    self._state.dropped_events += 1
                self._set_connected(False, str(exc))
                self._close(sc)
                sc = None
                # Do not requeue the failed control input.
                time.sleep(0.05)

        self._close(sc)
        self._set_connected(False, None)

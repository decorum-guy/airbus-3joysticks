from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from queue import Empty, Queue
from threading import Event, Lock, Thread
import time
from typing import Any


log = logging.getLogger(__name__)


@dataclass
class BridgeState:
    connected: bool = False
    last_error: str | None = None
    sent_events: int = 0
    dropped_events: int = 0


class SimConnectBridge:
    """Own the SimConnect handle on one background thread.

    Inputs are intentionally dropped while disconnected instead of queued for
    later replay. Replaying stale altitude/heading knob turns after the sim
    reconnects would be unsafe and surprising.
    """

    def __init__(self, reconnect_seconds: float = 2.0) -> None:
        self.reconnect_seconds = reconnect_seconds
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
            }

    def _set_connected(self, connected: bool, error: str | None = None) -> None:
        with self._lock:
            self._state.connected = connected
            self._state.last_error = error

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
        while not self._stop.is_set():
            if sc is None:
                try:
                    sc = SimConnect(name="Airbus3Joysticks")
                    self._set_connected(True, None)
                    log.info("Connected to MSFS via SimConnect")
                except Exception as exc:
                    self._set_connected(False, str(exc))
                    self._stop.wait(self.reconnect_seconds)
                    continue

            try:
                item = self._queue.get(timeout=0.25)
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

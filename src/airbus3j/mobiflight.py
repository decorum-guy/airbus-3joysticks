from __future__ import annotations

from ctypes import addressof, cast, c_void_p, create_string_buffer, string_at
import time
from typing import Any


class MobiFlightTransport:
    """Minimal MSFS2020 MobiFlight WASM command transport.

    MobiFlight's WASM module exposes ClientData command/response areas. We use
    the default areas only for a small presence probe and calculator-code
    execution. Production bindings should not rely on any aircraft-specific
    RPN/H-event until that exact action has been physically validated.

    The implementation intentionally does not create the ClientData areas. The
    WASM module owns them. If it is absent, mapping/requesting may still be
    accepted by SimConnect, but the MF.Ping handshake will time out and the
    transport stays unavailable.
    """

    STRING_SIZE = 256
    COMMAND_AREA_ID = 0xA3_01
    RESPONSE_AREA_ID = 0xA3_02
    COMMAND_DEFINITION_ID = 0xA3_11
    RESPONSE_DEFINITION_ID = 0xA3_12
    RESPONSE_REQUEST_ID = 0xA3_21

    CLIENT_DATA_PERIOD_ON_SET = 0x03
    CLIENT_DATA_REQUEST_FLAG_CHANGED = 0x01
    CLIENT_DATA_SET_FLAG_DEFAULT = 0x00
    SIMCONNECT_UNUSED = 0xFFFFFFFF

    def __init__(self, sc: Any) -> None:
        self.sc = sc
        self.available = False
        self.last_error: str | None = None
        self.last_response: str | None = None
        self.responses: list[str] = []
        self._recv_type: Any | None = None
        self._receiver_registered = False

    def state(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "last_error": self.last_error,
            "last_response": self.last_response,
        }

    def _receive_client_data(self, recv: Any) -> bool:
        if int(getattr(recv, "dwRequestID", -1)) != self.RESPONSE_REQUEST_ID:
            return False
        try:
            recv_type = self._recv_type or type(recv)
            offset = recv_type.dwData.offset
            raw = string_at(addressof(recv) + offset, self.STRING_SIZE)
            text = raw.split(b"\0", 1)[0].decode("ascii", errors="replace")
        except Exception as exc:
            self.last_error = f"response decode failed: {exc}"
            return True
        if text:
            self.last_response = text
            self.responses.append(text)
        return True

    def _map_areas(self) -> None:
        # Imports stay lazy so Linux CI can import the application without
        # loading the Windows-only SimConnect DLL.
        from simconnect.scdefs import RECV_CLIENT_DATA

        self._recv_type = RECV_CLIENT_DATA
        if not self._receiver_registered:
            self.sc.add_receiver(RECV_CLIENT_DATA, self._receive_client_data)
            self._receiver_registered = True

        self.sc.MapClientDataNameToID("MobiFlight.Command", self.COMMAND_AREA_ID)
        self.sc.MapClientDataNameToID("MobiFlight.Response", self.RESPONSE_AREA_ID)
        self.sc.AddToClientDataDefinition(
            self.COMMAND_DEFINITION_ID,
            0,
            self.STRING_SIZE,
            0.0,
            self.SIMCONNECT_UNUSED,
        )
        self.sc.AddToClientDataDefinition(
            self.RESPONSE_DEFINITION_ID,
            0,
            self.STRING_SIZE,
            0.0,
            self.SIMCONNECT_UNUSED,
        )
        self.sc.RequestClientData(
            self.RESPONSE_AREA_ID,
            self.RESPONSE_REQUEST_ID,
            self.RESPONSE_DEFINITION_ID,
            self.CLIENT_DATA_PERIOD_ON_SET,
            self.CLIENT_DATA_REQUEST_FLAG_CHANGED,
            0,
            0,
            0,
        )

    def send_command(self, command: str) -> bool:
        encoded = command.encode("ascii", errors="strict")
        if len(encoded) >= self.STRING_SIZE:
            raise ValueError(f"MobiFlight command must be shorter than {self.STRING_SIZE} bytes")
        buffer = create_string_buffer(self.STRING_SIZE)
        buffer.value = encoded
        try:
            self.sc.SetClientData(
                self.COMMAND_AREA_ID,
                self.COMMAND_DEFINITION_ID,
                self.CLIENT_DATA_SET_FLAG_DEFAULT,
                0,
                self.STRING_SIZE,
                cast(buffer, c_void_p),
            )
            return True
        except Exception as exc:
            self.last_error = f"SetClientData failed: {type(exc).__name__}: {exc}"
            return False

    def initialize(self, timeout_seconds: float = 1.5) -> bool:
        self.available = False
        self.last_error = None
        self.last_response = None
        self.responses.clear()
        try:
            self._map_areas()
        except Exception as exc:
            self.last_error = f"ClientData setup failed: {type(exc).__name__}: {exc}"
            return False

        # MobiFlight documents that the first SetClientData command after a
        # client starts can be ignored. Prime once, pump dispatch, then ping.
        self.send_command("MF.Ping")
        try:
            self.sc.receive(0.08)
        except Exception:
            pass
        if not self.send_command("MF.Ping"):
            return False

        deadline = time.monotonic() + max(0.2, float(timeout_seconds))
        while time.monotonic() < deadline:
            try:
                self.sc.receive(min(0.12, max(0.01, deadline - time.monotonic())))
            except Exception as exc:
                self.last_error = f"receive failed: {type(exc).__name__}: {exc}"
                break
            if any(response == "MF.Pong" for response in self.responses):
                self.available = True
                self.last_error = None
                return True

        if self.last_error is None:
            self.last_error = "MF.Pong timeout; MobiFlight WASM module is not responding"
        return False

    def execute_rpn(self, calculator_code: str) -> bool:
        if not self.available:
            self.last_error = "MobiFlight WASM transport is not available"
            return False
        return self.send_command("MF.SimVars.Set." + calculator_code)

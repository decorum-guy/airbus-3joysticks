from __future__ import annotations

from ctypes import addressof, c_void_p, cast, create_string_buffer, string_at
import os
import struct
import time
from typing import Any, Iterable

from .mobiflight import MobiFlightTransport


class MobiFlightVariableReader:
    """Read gauge calculator expressions through a dedicated MobiFlight client.

    MobiFlight reserves its default channels for the Connector application. An
    external SimConnect client should first register a unique client name via
    ``MF.Clients.Add.<name>`` and then use the WASM-created
    ``<name>.Command`` / ``<name>.LVars`` areas. Numeric expressions are
    returned as 4-byte floats at consecutive offsets in the LVars area.

    This reader is intentionally small and diagnostic-first. It does not own
    the SimConnect handle and must be used from the same thread that owns it.
    """

    STRING_SIZE = 256
    COMMAND_AREA_ID = 0xA4_01
    LVAR_AREA_ID = 0xA4_03
    COMMAND_DEFINITION_ID = 0xA4_11
    VARIABLE_DEFINITION_BASE = 0xA4_40
    VARIABLE_REQUEST_BASE = 0xA4_80

    CLIENT_DATA_PERIOD_ON_SET = 0x03
    CLIENT_DATA_REQUEST_FLAG_CHANGED = 0x01
    CLIENT_DATA_SET_FLAG_DEFAULT = 0x00
    SIMCONNECT_UNUSED = 0xFFFFFFFF

    MAX_FLOAT_VARIABLES = 128

    def __init__(
        self,
        sc: Any,
        transport: MobiFlightTransport,
        client_name: str | None = None,
    ) -> None:
        self.sc = sc
        self.transport = transport
        self.client_name = client_name or f"Airbus3J{os.getpid()}"
        self.available = False
        self.last_error: str | None = None
        self._receiver_registered = False
        self._recv_type: Any | None = None
        self._expressions: list[str] = []
        self._values: dict[str, float | None] = {}
        self._request_to_expression: dict[int, str] = {}

    def state(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "client_name": self.client_name,
            "last_error": self.last_error,
            "subscriptions": list(self._expressions),
            "values": dict(self._values),
        }

    def _receive_client_data(self, recv: Any) -> bool:
        request_id = int(getattr(recv, "dwRequestID", -1))
        expression = self._request_to_expression.get(request_id)
        if expression is None:
            return False
        try:
            recv_type = self._recv_type or type(recv)
            offset = recv_type.dwData.offset
            raw = string_at(addressof(recv) + offset, 4)
            value = struct.unpack("<f", raw)[0]
            self._values[expression] = float(value)
        except Exception as exc:
            self.last_error = f"variable decode failed: {type(exc).__name__}: {exc}"
        return True

    def _register_receiver(self) -> None:
        from simconnect.scdefs import RECV_CLIENT_DATA

        self._recv_type = RECV_CLIENT_DATA
        if not self._receiver_registered:
            self.sc.add_receiver(RECV_CLIENT_DATA, self._receive_client_data)
            self._receiver_registered = True

    def _send_client_command(self, command: str) -> bool:
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
            self.last_error = f"dedicated SetClientData failed: {type(exc).__name__}: {exc}"
            return False

    def initialize(self, timeout_seconds: float = 1.5) -> bool:
        self.available = False
        self.last_error = None
        if not self.transport.available:
            self.last_error = "MobiFlight command transport is not available"
            return False

        expected = f"MF.Clients.Add.{self.client_name}.Finished"
        start_index = len(self.transport.responses)
        if not self.transport.send_command(f"MF.Clients.Add.{self.client_name}"):
            self.last_error = self.transport.last_error or "client registration command failed"
            return False

        deadline = time.monotonic() + max(0.2, float(timeout_seconds))
        while time.monotonic() < deadline:
            if expected in self.transport.responses[start_index:]:
                break
            try:
                self.sc.receive(min(0.12, max(0.01, deadline - time.monotonic())))
            except Exception as exc:
                self.last_error = f"client registration receive failed: {type(exc).__name__}: {exc}"
                return False
        else:
            self.last_error = f"MobiFlight client registration timeout waiting for {expected}"
            return False

        try:
            self._register_receiver()
            self.sc.MapClientDataNameToID(f"{self.client_name}.Command", self.COMMAND_AREA_ID)
            self.sc.MapClientDataNameToID(f"{self.client_name}.LVars", self.LVAR_AREA_ID)
            self.sc.AddToClientDataDefinition(
                self.COMMAND_DEFINITION_ID,
                0,
                self.STRING_SIZE,
                0.0,
                self.SIMCONNECT_UNUSED,
            )
        except Exception as exc:
            self.last_error = f"dedicated ClientData setup failed: {type(exc).__name__}: {exc}"
            return False

        # MobiFlight documents that the first SetClientData command after a new
        # client starts can be ignored. Prime the dedicated command channel with
        # a harmless Ping before adding variables.
        self._send_client_command("MF.Ping")
        try:
            self.sc.receive(0.05)
        except Exception:
            pass

        self.available = True
        self.last_error = None
        return True

    def subscribe(self, expression: str) -> bool:
        if not self.available:
            self.last_error = "MobiFlight variable reader is not available"
            return False
        expression = str(expression).strip()
        if not expression:
            raise ValueError("expression must not be empty")
        if expression in self._values:
            return True
        if len(self._expressions) >= self.MAX_FLOAT_VARIABLES:
            raise ValueError(f"at most {self.MAX_FLOAT_VARIABLES} float variables are supported")

        index = len(self._expressions)
        definition_id = self.VARIABLE_DEFINITION_BASE + index
        request_id = self.VARIABLE_REQUEST_BASE + index
        offset = index * 4

        # Install the routing metadata before requesting data so an immediate
        # callback cannot arrive before we know where to store it.
        self._expressions.append(expression)
        self._values[expression] = None
        self._request_to_expression[request_id] = expression
        try:
            self.sc.AddToClientDataDefinition(
                definition_id,
                offset,
                4,
                0.0,
                self.SIMCONNECT_UNUSED,
            )
            self.sc.RequestClientData(
                self.LVAR_AREA_ID,
                request_id,
                definition_id,
                self.CLIENT_DATA_PERIOD_ON_SET,
                self.CLIENT_DATA_REQUEST_FLAG_CHANGED,
                0,
                0,
                0,
            )
        except Exception as exc:
            self.last_error = f"variable subscription setup failed: {type(exc).__name__}: {exc}"
            return False

        if not self._send_client_command("MF.SimVars.Add." + expression):
            return False
        return True

    def snapshot(
        self,
        expressions: Iterable[str],
        timeout_seconds: float = 1.0,
    ) -> dict[str, dict[str, Any]]:
        requested = [str(expression).strip() for expression in expressions]
        for expression in requested:
            if not self.subscribe(expression):
                continue

        deadline = time.monotonic() + max(0.05, float(timeout_seconds))
        while time.monotonic() < deadline:
            pending = [expression for expression in requested if self._values.get(expression) is None]
            if not pending:
                break
            try:
                self.sc.receive(min(0.10, max(0.01, deadline - time.monotonic())))
            except Exception as exc:
                self.last_error = f"variable receive failed: {type(exc).__name__}: {exc}"
                break

        result: dict[str, dict[str, Any]] = {}
        for expression in requested:
            value = self._values.get(expression)
            if value is None:
                result[expression] = {
                    "ok": False,
                    "value": None,
                    "error": self.last_error or "no value received before timeout",
                }
            else:
                result[expression] = {"ok": True, "value": value}
        return result

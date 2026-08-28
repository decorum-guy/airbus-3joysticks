from __future__ import annotations

from ctypes import create_string_buffer
from dataclasses import dataclass
from typing import Any
import hashlib
import time

import sdl2


AXES = {
    "left_x": sdl2.SDL_CONTROLLER_AXIS_LEFTX,
    "left_y": sdl2.SDL_CONTROLLER_AXIS_LEFTY,
    "right_x": sdl2.SDL_CONTROLLER_AXIS_RIGHTX,
    "right_y": sdl2.SDL_CONTROLLER_AXIS_RIGHTY,
    "trigger_left": sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT,
    "trigger_right": sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT,
}

BUTTONS = {
    "a": sdl2.SDL_CONTROLLER_BUTTON_A,
    "b": sdl2.SDL_CONTROLLER_BUTTON_B,
    "x": sdl2.SDL_CONTROLLER_BUTTON_X,
    "y": sdl2.SDL_CONTROLLER_BUTTON_Y,
    "back": sdl2.SDL_CONTROLLER_BUTTON_BACK,
    "guide": sdl2.SDL_CONTROLLER_BUTTON_GUIDE,
    "start": sdl2.SDL_CONTROLLER_BUTTON_START,
    "leftstick": sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK,
    "rightstick": sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK,
    "leftshoulder": sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER,
    "rightshoulder": sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
    "dpad_up": sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP,
    "dpad_down": sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN,
    "dpad_left": sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT,
    "dpad_right": sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
}


def _decode(value: bytes | None) -> str | None:
    if not value:
        return None
    return value.decode("utf-8", errors="replace")


def _axis(value: int) -> float:
    if value >= 0:
        return min(1.0, value / 32767.0)
    return max(-1.0, value / 32768.0)


@dataclass
class ControllerDevice:
    controller: Any
    instance_id: int
    key: str
    name: str
    serial: str | None
    path: str | None
    guid: str
    vendor_id: int
    product_id: int

    def public_identity(self) -> dict[str, Any]:
        return {
            "device_key": self.key,
            "name": self.name,
            "serial": self.serial,
            "path": self.path,
            "guid": self.guid,
            "vendor_id": self.vendor_id,
            "product_id": self.product_id,
            "identity_source": "serial" if self.serial else ("path" if self.path else "fallback"),
        }


class ControllerBackend:
    def __init__(self) -> None:
        flags = sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_HAPTIC | sdl2.SDL_INIT_EVENTS
        if sdl2.SDL_Init(flags) != 0:
            raise RuntimeError(_decode(sdl2.SDL_GetError()) or "SDL_Init failed")
        self.devices: dict[str, ControllerDevice] = {}
        self._last_count = -1
        self._last_scan_at = 0.0
        self.scan(force=True)

    def close(self) -> None:
        for device in list(self.devices.values()):
            try:
                sdl2.SDL_GameControllerClose(device.controller)
            except Exception:
                pass
        self.devices.clear()
        sdl2.SDL_QuitSubSystem(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_HAPTIC | sdl2.SDL_INIT_EVENTS)

    def _guid_string(self, joystick: Any) -> str:
        guid = sdl2.SDL_JoystickGetGUID(joystick)
        buf = create_string_buffer(33)
        sdl2.SDL_JoystickGetGUIDString(guid, buf, len(buf))
        return buf.value.decode("ascii", errors="replace")

    def _device_key(
        self,
        serial: str | None,
        path: str | None,
        guid: str,
        vendor_id: int,
        product_id: int,
        name: str,
        instance_id: int,
    ) -> str:
        if serial:
            raw = f"serial|{vendor_id:04x}|{product_id:04x}|{serial}"
            prefix = "serial"
        elif path:
            raw = f"path|{path}"
            prefix = "path"
        else:
            # Instance ID is intentionally included only as the last-resort key.
            # This key is not promised to survive reconnects.
            raw = f"fallback|{guid}|{vendor_id}|{product_id}|{name}|{instance_id}"
            prefix = "fallback"
        digest = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"{prefix}:{digest}"

    def scan(self, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self._last_scan_at < 1.0:
            return False
        self._last_scan_at = now
        sdl2.SDL_PumpEvents()
        count = int(sdl2.SDL_NumJoysticks())
        if not force and count == self._last_count:
            return False

        old_keys = set(self.devices)
        for device in list(self.devices.values()):
            try:
                sdl2.SDL_GameControllerClose(device.controller)
            except Exception:
                pass
        self.devices.clear()

        for index in range(count):
            if not sdl2.SDL_IsGameController(index):
                continue
            controller = sdl2.SDL_GameControllerOpen(index)
            if not controller:
                continue
            joystick = sdl2.SDL_GameControllerGetJoystick(controller)
            instance_id = int(sdl2.SDL_JoystickInstanceID(joystick))
            name = _decode(sdl2.SDL_GameControllerName(controller)) or f"Controller {index + 1}"
            serial = _decode(sdl2.SDL_JoystickGetSerial(joystick))
            # SDL_JoystickPath is available in SDL >= 2.24; packaged SDL is 2.32.x.
            path = _decode(sdl2.SDL_JoystickPath(joystick)) if hasattr(sdl2, "SDL_JoystickPath") else None
            guid = self._guid_string(joystick)
            vendor_id = int(sdl2.SDL_JoystickGetVendor(joystick)) if hasattr(sdl2, "SDL_JoystickGetVendor") else 0
            product_id = int(sdl2.SDL_JoystickGetProduct(joystick)) if hasattr(sdl2, "SDL_JoystickGetProduct") else 0
            key = self._device_key(serial, path, guid, vendor_id, product_id, name, instance_id)

            # In the extremely unlikely case of a collision, keep the devices distinct.
            if key in self.devices:
                key = f"{key}:{instance_id}"

            self.devices[key] = ControllerDevice(
                controller=controller,
                instance_id=instance_id,
                key=key,
                name=name,
                serial=serial,
                path=path,
                guid=guid,
                vendor_id=vendor_id,
                product_id=product_id,
            )

        self._last_count = count
        return old_keys != set(self.devices)

    def public_devices(self) -> list[dict[str, Any]]:
        return [device.public_identity() for device in self.devices.values()]

    def poll(self) -> dict[str, dict[str, Any]]:
        self.scan()
        sdl2.SDL_GameControllerUpdate()
        snapshots: dict[str, dict[str, Any]] = {}
        for key, device in self.devices.items():
            axes = {
                name: _axis(int(sdl2.SDL_GameControllerGetAxis(device.controller, axis_id)))
                for name, axis_id in AXES.items()
            }
            buttons = {
                name: bool(sdl2.SDL_GameControllerGetButton(device.controller, button_id))
                for name, button_id in BUTTONS.items()
            }
            snapshots[key] = {
                "identity": device.public_identity(),
                "axes": axes,
                "buttons": buttons,
            }
        return snapshots

    def rumble(self, device_key: str, strength: float, duration_ms: int) -> bool:
        device = self.devices.get(device_key)
        if not device or not hasattr(sdl2, "SDL_GameControllerRumble"):
            return False
        strength = min(1.0, max(0.0, strength))
        amplitude = int(strength * 0xFFFF)
        result = sdl2.SDL_GameControllerRumble(device.controller, amplitude, amplitude, int(duration_ms))
        return result == 0

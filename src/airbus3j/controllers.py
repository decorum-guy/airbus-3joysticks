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

for _name, _symbol in (
    ("misc1", "SDL_CONTROLLER_BUTTON_MISC1"),
    ("paddle1", "SDL_CONTROLLER_BUTTON_PADDLE1"),
    ("paddle2", "SDL_CONTROLLER_BUTTON_PADDLE2"),
    ("paddle3", "SDL_CONTROLLER_BUTTON_PADDLE3"),
    ("paddle4", "SDL_CONTROLLER_BUTTON_PADDLE4"),
    ("touchpad", "SDL_CONTROLLER_BUTTON_TOUCHPAD"),
):
    if hasattr(sdl2, _symbol):
        BUTTONS[_name] = getattr(sdl2, _symbol)


def _decode(value: bytes | None) -> str | None:
    if not value:
        return None
    return value.decode("utf-8", errors="replace")


def _sdl_error() -> str | None:
    try:
        return _decode(sdl2.SDL_GetError())
    except Exception:
        return None


def _clear_sdl_error() -> None:
    try:
        if hasattr(sdl2, "SDL_ClearError"):
            sdl2.SDL_ClearError()
    except Exception:
        pass


def _axis(value: int) -> float:
    if value >= 0:
        return min(1.0, value / 32767.0)
    return max(-1.0, value / 32768.0)


def _amplitude(strength: float) -> int:
    return int(min(1.0, max(0.0, float(strength))) * 0xFFFF)


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
    haptic: Any | None = None
    haptic_initialized: bool = False

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
    def __init__(self, enable_ps4_bt_rumble: bool = False) -> None:
        self.enable_ps4_bt_rumble = bool(enable_ps4_bt_rumble)
        # SDL requires this hint before controller initialization for extended
        # Bluetooth reports on PS4 controllers. It is opt-in because SDL warns
        # that extended reports can affect DirectInput users until power cycle.
        if self.enable_ps4_bt_rumble and hasattr(sdl2, "SDL_SetHint"):
            sdl2.SDL_SetHint(b"SDL_JOYSTICK_HIDAPI", b"1")
            sdl2.SDL_SetHint(b"SDL_JOYSTICK_HIDAPI_PS4", b"1")
            sdl2.SDL_SetHint(b"SDL_JOYSTICK_HIDAPI_PS4_RUMBLE", b"1")

        flags = sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_HAPTIC | sdl2.SDL_INIT_EVENTS
        if sdl2.SDL_Init(flags) != 0:
            raise RuntimeError(_decode(sdl2.SDL_GetError()) or "SDL_Init failed")
        self.devices: dict[str, ControllerDevice] = {}
        self._last_count = -1
        self._last_scan_at = 0.0
        self.scan(force=True)

    def _close_device(self, device: ControllerDevice) -> None:
        if device.haptic is not None:
            try:
                sdl2.SDL_HapticClose(device.haptic)
            except Exception:
                pass
            device.haptic = None
            device.haptic_initialized = False
        try:
            sdl2.SDL_GameControllerClose(device.controller)
        except Exception:
            pass

    def close(self) -> None:
        for device in list(self.devices.values()):
            self._close_device(device)
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
            self._close_device(device)
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
            path = _decode(sdl2.SDL_JoystickPath(joystick)) if hasattr(sdl2, "SDL_JoystickPath") else None
            guid = self._guid_string(joystick)
            vendor_id = int(sdl2.SDL_JoystickGetVendor(joystick)) if hasattr(sdl2, "SDL_JoystickGetVendor") else 0
            product_id = int(sdl2.SDL_JoystickGetProduct(joystick)) if hasattr(sdl2, "SDL_JoystickGetProduct") else 0
            key = self._device_key(serial, path, guid, vendor_id, product_id, name, instance_id)
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

    def rumble_capabilities(self, device_key: str) -> dict[str, Any]:
        device = self.devices.get(device_key)
        if not device:
            return {"ok": False, "error": "device not found"}
        joystick = sdl2.SDL_GameControllerGetJoystick(device.controller)
        result: dict[str, Any] = {
            "ok": True,
            "ps4_bt_extended_reports_enabled": self.enable_ps4_bt_rumble,
            "gamecontroller_has_rumble": None,
            "joystick_has_rumble": None,
            "joystick_is_haptic": None,
        }
        try:
            if hasattr(sdl2, "SDL_GameControllerHasRumble"):
                result["gamecontroller_has_rumble"] = bool(sdl2.SDL_GameControllerHasRumble(device.controller))
            if hasattr(sdl2, "SDL_JoystickHasRumble"):
                result["joystick_has_rumble"] = bool(sdl2.SDL_JoystickHasRumble(joystick))
            if hasattr(sdl2, "SDL_JoystickIsHaptic"):
                result["joystick_is_haptic"] = bool(sdl2.SDL_JoystickIsHaptic(joystick))
        except Exception as exc:
            result["capability_error"] = str(exc)
        return result

    def _ensure_haptic(self, device: ControllerDevice) -> tuple[Any | None, str | None]:
        if device.haptic is not None and device.haptic_initialized:
            return device.haptic, None
        if not all(
            hasattr(sdl2, name)
            for name in ("SDL_HapticOpenFromJoystick", "SDL_HapticRumbleInit", "SDL_HapticRumbleSupported")
        ):
            return None, "SDL haptic rumble API unavailable"
        joystick = sdl2.SDL_GameControllerGetJoystick(device.controller)
        _clear_sdl_error()
        haptic = sdl2.SDL_HapticOpenFromJoystick(joystick)
        if not haptic:
            return None, _sdl_error() or "SDL_HapticOpenFromJoystick failed"
        device.haptic = haptic
        supported = int(sdl2.SDL_HapticRumbleSupported(haptic))
        if supported <= 0:
            return None, _sdl_error() or "simple haptic rumble not supported"
        if int(sdl2.SDL_HapticRumbleInit(haptic)) != 0:
            return None, _sdl_error() or "SDL_HapticRumbleInit failed"
        device.haptic_initialized = True
        return haptic, None

    def rumble_method(
        self,
        device_key: str,
        method: str,
        low_strength: float,
        high_strength: float,
        duration_ms: int,
    ) -> dict[str, Any]:
        device = self.devices.get(device_key)
        if not device:
            return {"ok": False, "method": method, "error": "device not found"}
        low = _amplitude(low_strength)
        high = _amplitude(high_strength)
        duration = max(1, int(duration_ms))
        _clear_sdl_error()
        try:
            if method == "gamecontroller":
                if not hasattr(sdl2, "SDL_GameControllerRumble"):
                    return {"ok": False, "method": method, "error": "SDL_GameControllerRumble unavailable"}
                rc = int(sdl2.SDL_GameControllerRumble(device.controller, low, high, duration))
            elif method == "joystick":
                if not hasattr(sdl2, "SDL_JoystickRumble"):
                    return {"ok": False, "method": method, "error": "SDL_JoystickRumble unavailable"}
                joystick = sdl2.SDL_GameControllerGetJoystick(device.controller)
                rc = int(sdl2.SDL_JoystickRumble(joystick, low, high, duration))
            elif method == "haptic":
                if not hasattr(sdl2, "SDL_HapticRumblePlay"):
                    return {"ok": False, "method": method, "error": "SDL_HapticRumblePlay unavailable"}
                haptic, error = self._ensure_haptic(device)
                if haptic is None:
                    return {"ok": False, "method": method, "error": error}
                strength = max(float(low_strength), float(high_strength))
                rc = int(sdl2.SDL_HapticRumblePlay(haptic, min(1.0, max(0.0, strength)), duration))
            else:
                return {"ok": False, "method": method, "error": f"unknown rumble method: {method}"}
        except Exception as exc:
            return {"ok": False, "method": method, "error": f"{type(exc).__name__}: {exc}"}
        return {
            "ok": rc == 0,
            "method": method,
            "return_code": rc,
            "sdl_error": None if rc == 0 else _sdl_error(),
            "low_strength": float(low_strength),
            "high_strength": float(high_strength),
            "duration_ms": duration,
        }

    def rumble_detailed(self, device_key: str, strength: float, duration_ms: int) -> dict[str, Any]:
        attempts: list[dict[str, Any]] = []
        for method in ("gamecontroller", "joystick", "haptic"):
            attempt = self.rumble_method(device_key, method, strength, strength, duration_ms)
            attempts.append(attempt)
            if attempt.get("ok"):
                return {"ok": True, "selected_method": method, "attempts": attempts}
        return {"ok": False, "selected_method": None, "attempts": attempts}

    def rumble(self, device_key: str, strength: float, duration_ms: int) -> bool:
        return bool(self.rumble_detailed(device_key, strength, duration_ms).get("ok"))

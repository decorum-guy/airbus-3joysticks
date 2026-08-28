from __future__ import annotations

import logging
import socket

import uvicorn

from .config import ConfigStore
from .runtime import Runtime
from .web import create_app


log = logging.getLogger(__name__)


def _lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # UDP connect does not need to send data; it asks the OS which local
        # interface would be used. Fall back cleanly on isolated machines.
        sock.connect(("192.0.2.1", 9))
        return str(sock.getsockname()[0])
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "<windows-ip>"
    finally:
        sock.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = ConfigStore()
    cfg = config.snapshot()
    host = str(cfg["server"].get("host", "0.0.0.0"))
    port = int(cfg["server"].get("port", 8765))

    runtime = Runtime(config)
    app = create_app(runtime)

    print("\nAirbus 3 Joysticks")
    print(f"Config: {config.path}")
    print(f"Local panel: http://127.0.0.1:{port}")
    print(f"LAN panel:   http://{_lan_ip()}:{port}")
    print("Use the LAN address only on a trusted private network.\n")

    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()

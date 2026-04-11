"""Entry point: python -m apple_mcp [--http] [--port 3000] [--host 0.0.0.0]"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.transport_security import TransportSecuritySettings

from .server import mcp


def main():
    # Load .env from project root (for server-side deployment)
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

    transport = "stdio"
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--http":
            transport = "streamable-http"
        elif arg == "--port" and i < len(sys.argv) - 1:
            mcp.settings.port = int(sys.argv[i + 1])
        elif arg == "--host" and i < len(sys.argv) - 1:
            mcp.settings.host = sys.argv[i + 1]

    # HTTP mode defaults to 0.0.0.0 for remote access
    if transport == "streamable-http" and "--host" not in sys.argv:
        mcp.settings.host = "0.0.0.0"

    # Configure DNS rebinding protection for HTTP mode
    if transport == "streamable-http":
        allowed_hosts_env = os.environ.get("MCP_ALLOWED_HOSTS", "")
        if allowed_hosts_env:
            allowed_hosts = [h.strip() for h in allowed_hosts_env.split(",") if h.strip()]
            allowed_origins = [f"https://{h}" for h in allowed_hosts] + [f"http://{h}" for h in allowed_hosts]
            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=allowed_hosts,
                allowed_origins=allowed_origins,
            )
        elif mcp.settings.host == "0.0.0.0":
            # Disable DNS rebinding protection when binding to all interfaces
            # without explicit allowed hosts (reverse proxy should handle this)
            mcp.settings.transport_security = TransportSecuritySettings(
                enable_dns_rebinding_protection=False,
            )

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

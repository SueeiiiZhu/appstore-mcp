"""Entry point: python -m apple_mcp [--http] [--port 3000] [--host 0.0.0.0]"""

import sys
from pathlib import Path

from dotenv import load_dotenv

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

    mcp.run(transport=transport)


if __name__ == "__main__":
    main()

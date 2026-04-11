# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Apple App Store Connect Reports MCP Server — wraps the App Store Connect Reporting & Reviews API as an MCP server (stdio + streamable-HTTP). Parses gzipped TSV reports into structured JSON and provides higher-level aggregation tools (revenue, installs).

## Commands

```bash
# Install dependencies
uv sync

# Run MCP server (stdio mode, for Claude Desktop / Claude Code)
uv run python -m apple_mcp

# Run MCP server (HTTP mode)
uv run python -m apple_mcp --http --port 3000

# Run all tests
uv run pytest

# Run a single test
uv run pytest tests/test_parsers.py::test_parse_tsv_basic -v
```

## Architecture

```
src/apple_mcp/
  __main__.py   — CLI entry point, parses --http/--port/--host, calls mcp.run()
  server.py     — FastMCP instance, registers 6 MCP tools as thin wrappers
  auth.py       — JWT (ES256) token generation with in-memory cache (15 min TTL)
  client.py     — ApiClient: fetch_json() for REST endpoints, fetch_gzipped_report() for report downloads
  cache.py      — LRU in-memory ReportCache for immutable reports
  parsers.py    — TSV parsing + column mapping (SALES_COLUMN_MAP, FINANCE_COLUMN_MAP) + product-type constants
  tools/        — One module per MCP tool: revenue, installs, sales, subscriptions, finance, reviews
```

**Data flow:** MCP tool handler in `server.py` → tool function in `tools/` → `ApiClient` (with JWT from `auth.py`) → Apple API → gzip/JSON response → `parsers.py` → aggregation → JSON result.

**Key patterns:**
- Each tool module owns its own `ReportCache` instance; sales-based tools (`revenue`, `installs`) share the same fetch-and-cache pattern via a `_fetch_sales_rows` helper.
- `reviews` tool uses `fetch_json` (REST/JSON API), all other tools use `fetch_gzipped_report` (TSV API).
- Tool functions are pure async; the `server.py` wrappers handle `ApiError` → user-friendly messages.

## Environment Variables

Required (via `.env` or environment):
- `APP_STORE_CONNECT_ISSUER_ID`
- `APP_STORE_CONNECT_KEY_ID`
- `APP_STORE_CONNECT_PRIVATE_KEY_PATH` — path to `.p8` private key
- `APP_STORE_CONNECT_VENDOR_NUMBER`

## Testing

Tests use fixture files in `tests/fixtures/`. Currently covers TSV parsing only. Run with `uv run pytest`.

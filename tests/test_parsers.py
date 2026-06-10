"""Tests for TSV parsers."""

import gzip
from pathlib import Path

from apple_mcp.parsers import decode_report_bytes, parse_sales_report, parse_tsv

FIXTURES = Path(__file__).parent / "fixtures"


def test_decode_report_bytes_plain_text():
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    assert decode_report_bytes(raw.encode("utf-8")) == raw


def test_decode_report_bytes_gzip():
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    compressed = gzip.compress(raw.encode("utf-8"))
    assert decode_report_bytes(compressed, "sample_sales.tsv.gz") == raw


def test_parse_tsv_basic():
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    rows = parse_tsv(raw)
    assert len(rows) == 4
    assert rows[0]["Provider"] == "APPLE"
    assert rows[0]["Units"] == "10"
    assert rows[0]["Country Code"] == "US"


def test_parse_tsv_empty():
    assert parse_tsv("") == []


def test_parse_tsv_header_only():
    assert parse_tsv("Col1\tCol2\tCol3\n") == []


def test_parse_sales_report():
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    rows = parse_sales_report(raw)
    assert len(rows) == 4

    # Paid app download
    assert rows[0]["sku"] == "com.example.app"
    assert rows[0]["units"] == 10.0
    assert rows[0]["developer_proceeds"] == 6.99
    assert rows[0]["country_code"] == "US"
    assert rows[0]["product_type_identifier"] == "1"

    # Update
    assert rows[1]["product_type_identifier"] == "7"
    assert rows[1]["units"] == 5.0

    # JP
    assert rows[2]["country_code"] == "JP"
    assert rows[2]["developer_proceeds"] == 800.0

    # IAP
    assert rows[3]["product_type_identifier"] == "IA1"
    assert rows[3]["units"] == 20.0


def test_parse_sales_report_csv_with_apple_headers():
    raw = (FIXTURES / "sample_sales.tsv").read_text()
    csv_raw = raw.replace("\t", ",")
    rows = parse_sales_report(csv_raw)

    assert len(rows) == 4
    assert rows[0]["sku"] == "com.example.app"
    assert rows[0]["units"] == 10.0
    assert rows[0]["developer_proceeds"] == 6.99
    assert rows[2]["country_code"] == "JP"

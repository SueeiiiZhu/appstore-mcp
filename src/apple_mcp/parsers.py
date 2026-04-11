"""TSV report parsers for App Store Connect reports."""

import gzip
from typing import Any


def parse_tsv(raw: str) -> list[dict[str, str]]:
    """Parse a TSV string into a list of dicts keyed by header names."""
    lines = [line for line in raw.split("\n") if line.strip()]
    if len(lines) < 2:
        return []

    headers = lines[0].split("\t")
    rows = []
    for line in lines[1:]:
        values = line.split("\t")
        row = {h.strip(): (values[i].strip() if i < len(values) else "") for i, h in enumerate(headers)}
        rows.append(row)
    return rows


def parse_gzipped_tsv(data: bytes) -> list[dict[str, str]]:
    """Decompress gzipped data and parse as TSV."""
    text = gzip.decompress(data).decode("utf-8")
    return parse_tsv(text)


# Column mapping: Apple TSV header → our field name
SALES_COLUMN_MAP = {
    "Provider": "provider",
    "Provider Country": "provider_country",
    "SKU": "sku",
    "Developer": "developer",
    "Title": "title",
    "Version": "version",
    "Product Type Identifier": "product_type_identifier",
    "Units": "units",
    "Developer Proceeds": "developer_proceeds",
    "Begin Date": "begin_date",
    "End Date": "end_date",
    "Customer Currency": "customer_currency",
    "Country Code": "country_code",
    "Currency of Proceeds": "currency_of_proceeds",
    "Apple Identifier": "apple_identifier",
    "Customer Price": "customer_price",
    "Promo Code": "promo_code",
    "Parent Identifier": "parent_identifier",
    "Subscription": "subscription",
    "Period": "period",
    "Category": "category",
    "CMB": "cmb",
    "Device": "device",
    "Supported Platforms": "supported_platforms",
    "Proceeds Reason": "proceeds_reason",
    "Preserved Pricing": "preserved_pricing",
    "Client": "client",
    "Order Type": "order_type",
}

SALES_NUMERIC_FIELDS = {"units", "developer_proceeds", "customer_price"}

FINANCE_COLUMN_MAP = {
    "Start Date": "start_date",
    "End Date": "end_date",
    "Invoice Date": "invoice_date",
    "Partner Share": "partner_share",
    "Extended Partner Share": "extended_partner_share",
    "Partner Share Currency": "partner_share_currency",
    "Sales or Return": "sales_or_return",
    "Apple Identifier": "apple_identifier",
    "Artist/Show/Developer/Author": "artist_show_developer_author",
    "Title": "title",
    "Label/Studio/Network/Developer/Publisher": "label_studio_network_developer_publisher",
    "Grid": "grid",
    "Product Type Identifier": "product_type_identifier",
    "ISAN": "isan",
    "Country Of Sale": "country_of_sale",
    "Pre-order Flag": "pre_order_flag",
    "Promo Code": "promo_code",
    "Customer Price": "customer_price",
    "Customer Currency": "customer_currency",
    "Quantity": "quantity",
}

FINANCE_NUMERIC_FIELDS = {"partner_share", "extended_partner_share", "customer_price", "quantity"}


def _map_row(
    raw_row: dict[str, str],
    column_map: dict[str, str],
    numeric_fields: set[str],
) -> dict[str, Any]:
    mapped: dict[str, Any] = {}
    for tsv_header, field_name in column_map.items():
        value = raw_row.get(tsv_header, "")
        if field_name in numeric_fields:
            mapped[field_name] = float(value) if value else 0.0
        else:
            mapped[field_name] = value
    return mapped


def parse_sales_report(raw: str) -> list[dict[str, Any]]:
    """Parse sales report TSV into typed dicts."""
    return [_map_row(row, SALES_COLUMN_MAP, SALES_NUMERIC_FIELDS) for row in parse_tsv(raw)]


def parse_finance_report(raw: str) -> list[dict[str, Any]]:
    """Parse finance report TSV into typed dicts."""
    return [_map_row(row, FINANCE_COLUMN_MAP, FINANCE_NUMERIC_FIELDS) for row in parse_tsv(raw)]


# Product Type Identifier sets
INSTALL_PRODUCT_TYPES = {"1", "1-B", "1E", "1EP", "1EU", "1F", "1T", "F1", "F1-B"}
UPDATE_PRODUCT_TYPES = {"7", "7F", "7T", "F7"}
REDOWNLOAD_PRODUCT_TYPES = {"3", "3F"}

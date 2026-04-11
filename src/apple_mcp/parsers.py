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

SUBSCRIPTION_COLUMN_MAP = {
    "App Name": "app_name",
    "App Apple ID": "app_apple_id",
    "Subscription Name": "subscription_name",
    "Subscription Apple ID": "subscription_apple_id",
    "Subscription Group ID": "subscription_group_id",
    "Standard Subscription Duration": "standard_subscription_duration",
    "Subscription Offer Name": "subscription_offer_name",
    "Promotional Offer ID": "promotional_offer_id",
    "Customer Price": "customer_price",
    "Customer Currency": "customer_currency",
    "Developer Proceeds": "developer_proceeds",
    "Proceeds Currency": "proceeds_currency",
    "Preserved Pricing": "preserved_pricing",
    "Proceeds Reason": "proceeds_reason",
    "Client": "client",
    "Device": "device",
    "State": "state",
    "Country": "country",
    "Active Standard Price Subscriptions": "active_standard_price",
    "Active Free Trial Introductory Offer Subscriptions": "active_free_trial_intro",
    "Active Pay Up Front Introductory Offer Subscriptions": "active_pay_up_front_intro",
    "Active Pay as You Go Introductory Offer Subscriptions": "active_pay_as_you_go_intro",
    "Free Trial Promotional Offer Subscriptions": "free_trial_promo",
    "Pay Up Front Promotional Offer Subscriptions": "pay_up_front_promo",
    "Pay As You Go Promotional Offer Subscriptions": "pay_as_you_go_promo",
    "Free Trial Offer Code Subscriptions": "free_trial_offer_code",
    "Pay Up Front Offer Code Subscriptions": "pay_up_front_offer_code",
    "Pay As You Go Offer Code Subscriptions": "pay_as_you_go_offer_code",
    "Marketing Opt-Ins": "marketing_opt_ins",
    "Billing Retry": "billing_retry",
    "Grace Period": "grace_period",
    "Subscribers": "subscribers",
    "Free Trial Win-Back Offers": "free_trial_win_back",
    "Pay Up Front Win-Back Offers": "pay_up_front_win_back",
    "Pay As You Go Win-Back Offers": "pay_as_you_go_win_back",
}

SUBSCRIPTION_NUMERIC_FIELDS = {
    "customer_price", "developer_proceeds",
    "active_standard_price", "active_free_trial_intro",
    "active_pay_up_front_intro", "active_pay_as_you_go_intro",
    "free_trial_promo", "pay_up_front_promo", "pay_as_you_go_promo",
    "free_trial_offer_code", "pay_up_front_offer_code", "pay_as_you_go_offer_code",
    "marketing_opt_ins", "billing_retry", "grace_period", "subscribers",
    "free_trial_win_back", "pay_up_front_win_back", "pay_as_you_go_win_back",
}

SUBSCRIPTION_EVENT_COLUMN_MAP = {
    "Event Date": "event_date",
    "Event": "event",
    "App Name": "app_name",
    "App Apple ID": "app_apple_id",
    "Subscription Name": "subscription_name",
    "Subscription Apple ID": "subscription_apple_id",
    "Subscription Group ID": "subscription_group_id",
    "Standard Subscription Duration": "standard_subscription_duration",
    "Subscription Offer Type": "subscription_offer_type",
    "Subscription Offer Duration": "subscription_offer_duration",
    "Marketing Opt-In": "marketing_opt_in",
    "Marketing Opt-In Duration": "marketing_opt_in_duration",
    "Preserved Pricing": "preserved_pricing",
    "Proceeds Reason": "proceeds_reason",
    "Subscription Offer Name": "subscription_offer_name",
    "Promotional Offer ID": "promotional_offer_id",
    "Consecutive Paid Periods": "consecutive_paid_periods",
    "Original Start Date": "original_start_date",
    "Device": "device",
    "Client": "client",
    "State": "state",
    "Country": "country",
    "Previous Subscription Name": "previous_subscription_name",
    "Previous Subscription Apple ID": "previous_subscription_apple_id",
    "Days Before Canceling": "days_before_canceling",
    "Cancellation Reason": "cancellation_reason",
    "Days Canceled": "days_canceled",
    "Quantity": "quantity",
    "Paid Service Days Recovered": "paid_service_days_recovered",
}

SUBSCRIPTION_EVENT_NUMERIC_FIELDS = {
    "consecutive_paid_periods", "days_before_canceling", "days_canceled",
    "quantity", "paid_service_days_recovered",
}


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


def parse_subscription_report(raw: str) -> list[dict[str, Any]]:
    """Parse subscription report TSV into typed dicts."""
    return [_map_row(row, SUBSCRIPTION_COLUMN_MAP, SUBSCRIPTION_NUMERIC_FIELDS) for row in parse_tsv(raw)]


def parse_subscription_event_report(raw: str) -> list[dict[str, Any]]:
    """Parse subscription event report TSV into typed dicts."""
    return [_map_row(row, SUBSCRIPTION_EVENT_COLUMN_MAP, SUBSCRIPTION_EVENT_NUMERIC_FIELDS) for row in parse_tsv(raw)]


# Product Type Identifier sets
INSTALL_PRODUCT_TYPES = {"1", "1-B", "1E", "1EP", "1EU", "1F", "1T", "F1", "F1-B"}
UPDATE_PRODUCT_TYPES = {"7", "7F", "7T", "F7"}
REDOWNLOAD_PRODUCT_TYPES = {"3", "3F"}

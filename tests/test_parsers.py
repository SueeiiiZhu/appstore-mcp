"""Tests for TSV parsers."""

import gzip
from pathlib import Path

from apple_mcp.parsers import (
    decode_report_bytes,
    format_sales_report_rows,
    format_subscription_report_rows,
    parse_sales_report,
    parse_subscription_report,
    parse_tsv,
)

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


def test_parse_sales_report_csv_with_transformed_headers():
    raw = (
        "Provider,ProviderCountry,SKU,Developer,Title,ContentType,Version,"
        "ProductTypeIdentifier,Units,DeveloperProceeds,BeginDate,EndDate,"
        "CustomerCurrency,Country,CountryCode,CurrencyOfProceeds,"
        "AppleIdentifier,CustomerPrice,PromoCode,ParentIdentifier,"
        "Subscription,Period,Category,CMB,Device,SupportedPlatforms,"
        "ProceedsReason,PreservedPricing,Client,OrderType,AppName,"
        "ExchangeRate,WithholdingTaxRate,WithholdingTax\n"
        "APPLE,US,com.delta.cube.solver,Delta Software,CubeSolver,APP,3.3.3,"
        "1,2,1.38,2024-04-21,2024-04-21,USD,United States,US,USD,123456789,"
        "1.99,PROMO,parent-id,Monthly,1 Month,Utilities,CMB123,iPhone,iOS,"
        "Standard,false,App Store,Purchase,CubeSolver,1,0,0\n"
    )

    rows = parse_sales_report(raw)

    assert len(rows) == 1
    assert rows[0]["provider_country"] == "US"
    assert rows[0]["content_type"] == "APP"
    assert rows[0]["product_type_identifier"] == "1"
    assert rows[0]["developer_proceeds"] == 1.38
    assert rows[0]["begin_date"] == "2024-04-21"
    assert rows[0]["country"] == "United States"
    assert rows[0]["country_code"] == "US"
    assert rows[0]["currency_of_proceeds"] == "USD"
    assert rows[0]["apple_identifier"] == "123456789"
    assert rows[0]["customer_price"] == 1.99
    assert rows[0]["supported_platforms"] == "iOS"
    assert rows[0]["order_type"] == "Purchase"
    assert rows[0]["app_name"] == "CubeSolver"
    assert rows[0]["exchange_rate"] == 1.0
    assert rows[0]["withholding_tax_rate"] == 0.0
    assert rows[0]["withholding_tax"] == 0.0


def test_format_sales_report_rows_uses_transformed_headers():
    raw = (FIXTURES / "sample_sales.tsv").read_text()

    formatted_rows = format_sales_report_rows(parse_sales_report(raw))

    assert len(formatted_rows) == 4
    assert formatted_rows[0]["SKU"] == "com.example.app"
    assert formatted_rows[0]["ProviderCountry"] == "US"
    assert formatted_rows[0]["ProductTypeIdentifier"] == "1"
    assert formatted_rows[0]["CustomerCurrency"] == "USD"
    assert formatted_rows[0]["CountryCode"] == "US"
    assert formatted_rows[0]["SupportedPlatforms"] == "iOS"


def test_format_subscription_report_rows_uses_transformed_headers():
    raw = (
        "App Name\tSubscription Apple ID\tCustomer Price\tCustomer Currency\tDeveloper Proceeds\n"
        "CubeSolver Pro\t123456789\t9.99\tUSD\t6.99\n"
    )

    rows = parse_subscription_report(raw)
    formatted_rows = format_subscription_report_rows(rows)

    assert rows[0]["app_name"] == "CubeSolver Pro"
    assert rows[0]["subscription_apple_id"] == "123456789"
    assert formatted_rows[0]["AppName"] == "CubeSolver Pro"
    assert formatted_rows[0]["SubscriptionAppleID"] == "123456789"
    assert formatted_rows[0]["CustomerPrice"] == 9.99
    assert formatted_rows[0]["DeveloperProceeds"] == 6.99

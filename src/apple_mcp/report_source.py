"""Resolve report content from Apple API or local archives."""

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .client import ApiClient
from .parsers import decode_report_bytes

ReportSource = Literal["auto", "api", "local"]

LOCAL_REPORT_DIR_ENV = "APP_STORE_REPORT_LOCAL_DIR"
_ALLOWED_SUFFIXES = (".gz", ".gzip", ".tsv", ".txt")

_SPECIAL_ALIASES = {
    "SALES": {"sales", "sale", "s"},
    "SUBSCRIPTION": {"subscription", "subscriptions"},
    "SUBSCRIPTION_EVENT": {
        "subscription_event",
        "subscriptionevent",
        "subscriptions_event",
        "subscriptions-event",
        "subscriptionsevent",
        "event",
        "events",
    },
    "SUBSCRIBER": {"subscriber", "subscribers"},
    "SUBSCRIPTION_OFFER_REDEMPTION": {
        "subscription_offer_redemption",
        "subscriptionofferredemption",
        "offer_redemption",
        "offerredemption",
        "offer",
        "redemption",
    },
    "FINANCIAL": {
        "financial",
        "financial_extended",
        "financialextended",
        "finance",
        "finances",
        "f",
    },
    "SUMMARY": {"summary", "sum"},
    "DETAILED": {"detailed", "detail"},
    "SUMMARY_INSTALL_TYPE": {"summary_install_type", "install_type", "installtype"},
    "SUMMARY_TERRITORY": {"summary_territory", "territory"},
    "SUMMARY_CHANNEL": {"summary_channel", "channel"},
    "DAILY": {"daily", "day", "d"},
    "WEEKLY": {"weekly", "week", "w"},
    "MONTHLY": {"monthly", "month", "m"},
    "YEARLY": {"yearly", "year", "y"},
}

_PREFERRED_LOCAL_ROOTS = {
    "FINANCIAL": ("financial_extended", "financial", "finance"),
    "SUBSCRIPTION_EVENT": ("subscriptions_event", "sales"),
    "SUBSCRIPTION": ("sales", "subscriptions"),
    "SUBSCRIBER": ("sales", "subscriptions"),
    "SUBSCRIPTION_OFFER_REDEMPTION": ("sales", "subscriptions"),
    "SALES": ("sales",),
}

_CONFLICTING_REPORT_TYPES = (
    "SUBSCRIPTION",
    "SUBSCRIPTION_EVENT",
    "SUBSCRIBER",
    "SUBSCRIPTION_OFFER_REDEMPTION",
)


class ReportSourceError(Exception):
    """Raised when a report source cannot be resolved."""


@dataclass(frozen=True)
class ReportLocation:
    source: Literal["api", "local"]
    cache_fragment: str
    path: str
    params: dict[str, str] | None = None
    local_path: Path | None = None


@dataclass(frozen=True)
class LocalReportQuery:
    report_type: str
    report_date: str
    report_sub_type: str | None = None
    frequency: str | None = None
    region_code: str | None = None
    vendor_number: str | None = None
    version: str | None = None

    @property
    def effective_type(self) -> str:
        if self.report_type == "SALES" and self.report_sub_type in _CONFLICTING_REPORT_TYPES:
            return self.report_sub_type
        return self.report_type

    def describe(self) -> str:
        parts = [self.effective_type]
        if self.report_sub_type and self.report_sub_type != self.effective_type:
            parts.append(self.report_sub_type)
        if self.frequency:
            parts.append(self.frequency)
        parts.append(self.report_date)
        if self.region_code:
            parts.append(self.region_code)
        return " ".join(parts)


async def load_report_text(client: ApiClient, location: ReportLocation) -> str:
    if location.source == "local":
        if location.local_path is None:
            raise ReportSourceError("Resolved local report is missing its file path.")
        return decode_report_bytes(location.local_path.read_bytes(), location.local_path.name)

    return await client.fetch_gzipped_report(location.path, location.params or {})


def resolve_sales_report_source(
    client: ApiClient,
    report_date: str,
    report_type: str = "SALES",
    report_sub_type: str = "SUMMARY",
    date_type: str = "DAILY",
    source: ReportSource = "auto",
    version: str | None = None,
) -> ReportLocation:
    source = _validate_source(source)
    root = _get_local_report_root(source)
    query = LocalReportQuery(
        report_type=report_type,
        report_sub_type=report_sub_type,
        frequency=date_type,
        report_date=report_date,
        vendor_number=client.vendor_number or None,
        version=version,
    )

    if root is not None:
        local_path = _find_local_report(root, query)
        if local_path is not None:
            return _build_local_location(local_path)
        if source == "local":
            raise ReportSourceError(
                f"No matching local report found under {root} for {query.describe()}."
            )
    elif source == "local":
        raise ReportSourceError(
            f"Local report source requested, but {LOCAL_REPORT_DIR_ENV} is not set."
        )

    return ReportLocation(
        source="api",
        cache_fragment="api",
        path="/v1/salesReports",
        params={
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": report_type,
            "filter[reportSubType]": report_sub_type,
            "filter[reportDate]": report_date,
            "filter[frequency]": date_type,
            **({"filter[version]": version} if version else {}),
        },
    )


def resolve_finance_report_source(
    client: ApiClient,
    report_date: str,
    region_code: str = "ZZ",
    source: ReportSource = "auto",
) -> ReportLocation:
    source = _validate_source(source)
    root = _get_local_report_root(source)
    query = LocalReportQuery(
        report_type="FINANCIAL",
        report_date=report_date,
        region_code=region_code,
        vendor_number=client.vendor_number or None,
    )

    if root is not None:
        local_path = _find_local_report(root, query)
        if local_path is not None:
            return _build_local_location(local_path)
        if source == "local":
            raise ReportSourceError(
                f"No matching local report found under {root} for {query.describe()}."
            )
    elif source == "local":
        raise ReportSourceError(
            f"Local report source requested, but {LOCAL_REPORT_DIR_ENV} is not set."
        )

    return ReportLocation(
        source="api",
        cache_fragment="api",
        path="/v1/financeReports",
        params={
            "filter[vendorNumber]": client.vendor_number,
            "filter[reportType]": "FINANCIAL",
            "filter[reportDate]": report_date,
            "filter[regionCode]": region_code,
        },
    )


def list_local_reports(
    *,
    report_type: str | None = None,
    report_sub_type: str | None = None,
    date_type: str | None = None,
    report_date_prefix: str = "",
    region_code: str | None = None,
    vendor_number: str | None = None,
    path_prefix: str = "",
    max_results: int = 50,
) -> dict[str, Any]:
    root = _get_local_report_root("local")
    if root is None:
        raise ReportSourceError(
            f"Local report listing requires {LOCAL_REPORT_DIR_ENV} to be set to a real directory."
        )

    normalized_report_type = report_type.upper() if report_type else None
    normalized_report_sub_type = report_sub_type.upper() if report_sub_type else None
    normalized_date_type = date_type.upper() if date_type else None
    normalized_region_code = region_code.lower() if region_code else None
    normalized_vendor_number = vendor_number.lower() if vendor_number else None
    normalized_date_prefix = report_date_prefix.lower().strip()
    normalized_path_prefix = path_prefix.strip().strip("/").lower()
    capped_max_results = max(1, min(max_results, 500))

    search_roots = _candidate_roots(root, normalized_report_type) if normalized_report_type else [root]
    files: list[dict[str, Any]] = []
    seen: set[Path] = set()

    for search_root in search_roots:
        for candidate in search_root.rglob("*"):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue

            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)

            if not str(resolved).lower().endswith(_ALLOWED_SUFFIXES):
                continue
            try:
                relative_path = resolved.relative_to(root).as_posix()
            except ValueError:
                continue

            if normalized_path_prefix and not relative_path.lower().startswith(normalized_path_prefix):
                continue
            if not _matches_local_report_filters(
                relative_path,
                report_type=normalized_report_type,
                report_sub_type=normalized_report_sub_type,
                date_type=normalized_date_type,
                report_date_prefix=normalized_date_prefix,
                region_code=normalized_region_code,
                vendor_number=normalized_vendor_number,
            ):
                continue

            stat = resolved.stat()
            files.append(
                {
                    "name": relative_path,
                    "size": stat.st_size,
                    "updated": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat().replace("+00:00", "Z"),
                    "top_level_dir": relative_path.split("/", 1)[0],
                }
            )

    files.sort(key=lambda item: item["name"])
    total_count = len(files)
    returned_files = files[:capped_max_results]

    return {
        "root": str(root),
        "total_count": total_count,
        "returned_count": len(returned_files),
        "truncated": total_count > capped_max_results,
        "filters": {
            "report_type": normalized_report_type,
            "report_sub_type": normalized_report_sub_type,
            "date_type": normalized_date_type,
            "report_date_prefix": normalized_date_prefix or None,
            "region_code": normalized_region_code,
            "vendor_number": normalized_vendor_number,
            "path_prefix": normalized_path_prefix or None,
        },
        "files": returned_files,
    }


def _build_local_location(path: Path) -> ReportLocation:
    stat = path.stat()
    return ReportLocation(
        source="local",
        cache_fragment=f"local:{path}:{stat.st_mtime_ns}:{stat.st_size}",
        path=str(path),
        local_path=path,
    )


def _validate_source(source: str) -> ReportSource:
    if source not in {"auto", "api", "local"}:
        raise ReportSourceError(f"Invalid source '{source}'. Use auto, api, or local.")
    return source  # type: ignore[return-value]


def _get_local_report_root(source: ReportSource) -> Path | None:
    if source == "api":
        return None

    value = os.environ.get(LOCAL_REPORT_DIR_ENV, "").strip()
    if not value:
        return None

    root = Path(value).expanduser().resolve()
    if not root.is_dir():
        raise ReportSourceError(
            f"{LOCAL_REPORT_DIR_ENV} points to '{value}', but that directory does not exist."
        )
    return root


def _find_local_report(root: Path, query: LocalReportQuery) -> Path | None:
    scored_candidates: list[tuple[int, Path]] = []
    seen: set[Path] = set()

    for search_root in _candidate_roots(root, query.effective_type):
        for candidate in search_root.rglob("*"):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue

            if resolved in seen or not resolved.is_file():
                continue
            seen.add(resolved)

            if not str(resolved).lower().endswith(_ALLOWED_SUFFIXES):
                continue
            try:
                resolved.relative_to(root)
            except ValueError:
                continue

            score = _score_candidate(resolved, root, query)
            if score > 0:
                scored_candidates.append((score, resolved))

    if not scored_candidates:
        return None

    scored_candidates.sort(key=lambda item: (item[0], item[1].stat().st_mtime_ns), reverse=True)
    best_score, best_path = scored_candidates[0]
    if best_score < 120:
        return None

    if len(scored_candidates) > 1 and scored_candidates[1][0] == best_score:
        second_path = scored_candidates[1][1]
        raise ReportSourceError(
            "Multiple local report files matched "
            f"{query.describe()}: {best_path.relative_to(root)} and {second_path.relative_to(root)}"
        )

    return best_path


def _matches_local_report_filters(
    relative_path: str,
    *,
    report_type: str | None,
    report_sub_type: str | None,
    date_type: str | None,
    report_date_prefix: str,
    region_code: str | None,
    vendor_number: str | None,
) -> bool:
    lowered = relative_path.lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", lowered) if token}

    if report_type and not _matches_any(lowered, tokens, _aliases_for(report_type)):
        return False
    if report_sub_type and not _matches_any(lowered, tokens, _aliases_for(report_sub_type)):
        return False
    if date_type and not _matches_any(lowered, tokens, _aliases_for(date_type)):
        return False
    if report_date_prefix and report_date_prefix not in lowered:
        return False
    if region_code and not _matches_any(lowered, tokens, {region_code}):
        return False
    if vendor_number and not _matches_any(lowered, tokens, {vendor_number}):
        return False
    return True


def _candidate_roots(root: Path, effective_type: str) -> list[Path]:
    preferred_dirs = [root / name for name in _PREFERRED_LOCAL_ROOTS.get(effective_type, ("sales",))]

    roots: list[Path] = []
    for candidate in [*preferred_dirs, root]:
        if candidate.is_dir() and candidate not in roots:
            roots.append(candidate)
    return roots


def _score_candidate(path: Path, root: Path, query: LocalReportQuery) -> int:
    relative = path.relative_to(root).as_posix().lower()
    tokens = {token for token in re.split(r"[^a-z0-9]+", relative) if token}

    if not _matches_any(relative, tokens, _date_aliases(query.report_date)):
        return 0
    if _has_conflicting_type(relative, tokens, query.effective_type):
        return 0

    score = 100
    top_level = relative.split("/", 1)[0]

    if _matches_any(relative, tokens, _aliases_for(query.effective_type)):
        score += 40
    if top_level in _PREFERRED_LOCAL_ROOTS.get(query.effective_type, ()):
        score += 30
    if query.report_sub_type and query.report_sub_type != query.effective_type:
        if _matches_any(relative, tokens, _aliases_for(query.report_sub_type)):
            score += 20
    if query.frequency and _matches_any(relative, tokens, _aliases_for(query.frequency)):
        score += 15
    if query.region_code and _matches_any(relative, tokens, {query.region_code.lower()}):
        score += 25
    if query.vendor_number and _matches_any(relative, tokens, {query.vendor_number.lower()}):
        score += 15
    if query.version and _matches_any(relative, tokens, _version_aliases(query.version)):
        score += 10

    return score


def _matches_any(text: str, tokens: set[str], aliases: set[str]) -> bool:
    for alias in aliases:
        normalized = alias.lower()
        if len(normalized) == 1:
            if normalized in tokens:
                return True
        elif normalized in tokens or normalized in text:
            return True
    return False


def _aliases_for(value: str) -> set[str]:
    base = value.lower()
    aliases = {
        base,
        base.replace("_", "-"),
        base.replace("_", ""),
    }
    aliases.update(_SPECIAL_ALIASES.get(value.upper(), set()))
    return aliases


def _date_aliases(report_date: str) -> set[str]:
    if len(report_date) == 10:
        return {
            report_date.lower(),
            report_date.replace("-", "_").lower(),
            report_date.replace("-", "").lower(),
        }
    return {
        report_date.lower(),
        report_date.replace("-", "_").lower(),
        report_date.replace("-", "").lower(),
    }


def _version_aliases(version: str) -> set[str]:
    return {
        version.lower(),
        version.replace("_", "-").lower(),
        version.replace("_", "").lower(),
    }


def _matches_specific_type_name(text: str, effective_type: str) -> bool:
    specific_aliases = {
        "SUBSCRIPTION_EVENT": {
            "subscription_event",
            "subscriptionevent",
            "subscriptions_event",
            "subscriptions-event",
            "subscriptionsevent",
        },
        "SUBSCRIBER": {"subscriber", "subscribers"},
        "SUBSCRIPTION_OFFER_REDEMPTION": {
            "subscription_offer_redemption",
            "subscriptionofferredemption",
            "offer_redemption",
            "offerredemption",
        },
    }
    return any(alias in text for alias in specific_aliases.get(effective_type, set()))


def _has_conflicting_type(text: str, tokens: set[str], effective_type: str) -> bool:
    if effective_type in _CONFLICTING_REPORT_TYPES:
        for other in _CONFLICTING_REPORT_TYPES:
            if other == effective_type:
                continue
            if (
                other == "SUBSCRIPTION"
                and effective_type != "SUBSCRIPTION"
                and _matches_specific_type_name(text, effective_type)
            ):
                continue
            if _matches_any(text, tokens, _aliases_for(other)):
                return True
    elif effective_type == "SALES":
        for other in _CONFLICTING_REPORT_TYPES:
            if _matches_any(text, tokens, _aliases_for(other)):
                return True
    return False

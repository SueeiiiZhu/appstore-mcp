"""Customer reviews tool."""

from typing import Any

from ..client import ApiClient


async def get_customer_reviews(
    client: ApiClient,
    app_id: str,
    limit: int = 20,
    sort: str = "-createdDate",
    rating: int | None = None,
) -> dict[str, Any]:
    params: dict[str, str] = {
        "limit": str(min(limit, 200)),
        "sort": sort,
    }
    if rating is not None:
        params["filter[rating]"] = str(rating)

    data = await client.fetch_json(f"/v1/apps/{app_id}/customerReviews", params)

    reviews = [
        {
            "id": item["id"],
            "title": item["attributes"]["title"],
            "body": item["attributes"]["body"],
            "rating": item["attributes"]["rating"],
            "reviewer_nickname": item["attributes"]["reviewerNickname"],
            "territory": item["attributes"]["territory"],
            "created_date": item["attributes"]["createdDate"],
        }
        for item in data.get("data", [])
    ]

    total = data.get("meta", {}).get("paging", {}).get("total", len(reviews))
    return {"reviews": reviews, "total": total}

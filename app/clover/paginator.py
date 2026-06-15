from typing import Generator

from app.clover.query_params import DEFAULT_PAGE_SIZE, QueryParams, merge_params, page_params


def paginate(
    client,
    path: str,
    page_size: int = DEFAULT_PAGE_SIZE,
    extra_params: QueryParams | None = None,
) -> Generator[list, None, None]:
    """
    Yields pages of elements from a Clover list endpoint.
    Stops when the API returns fewer items than the requested page size.

    Each page uses limit/offset pagination (default limit=1000), matching the
    production PowerShell client.
    """
    offset = 0
    while True:
        params = page_params(limit=page_size, offset=offset)
        if extra_params:
            params = merge_params(params, extra_params)

        data = client.get(path, params=params)
        elements = data.get("elements", [])

        yield elements

        if len(elements) < page_size:
            break

        offset += page_size

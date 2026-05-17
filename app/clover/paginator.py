from typing import Generator


def paginate(
    client,
    path: str,
    page_size: int = 1000,
    extra_params: dict = None,
) -> Generator[list, None, None]:
    """
    Yields pages of elements from a Clover list endpoint.
    Stops when the API returns fewer items than the requested page size.
    """
    offset = 0
    while True:
        params = {"limit": page_size, "offset": offset}
        if extra_params:
            params.update(extra_params)

        data = client.get(path, params=params)
        elements = data.get("elements", [])

        yield elements

        if len(elements) < page_size:
            break

        offset += page_size

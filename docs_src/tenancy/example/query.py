import httpx


async def query():
    response = await httpx.get("/products", headers={"tenant": "saffier"})

    # Total products created for `saffier` schema
    assert len(response.json()) == 10

    # Response for the "shared", no tenant associated.
    response = await httpx.get("/products")
    assert len(response.json()) == 25

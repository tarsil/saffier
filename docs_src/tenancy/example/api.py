from typing import List

from ravyn import Ravyn, Gateway, JSONResponse, get

import saffier

database = saffier.Database("<TOUR-CONNECTION-STRING>")
models = saffier.Registry(database=database)


@get("/products")
async def products() -> JSONResponse:
    """
    Returns the products associated to a tenant or
    all the "shared" products if tenant is None.
    """
    products = await Product.query.all()
    products = [product.pk for product in products]
    return JSONResponse(products)


app = Ravyn(
    routes=[Gateway(handler=products)],
    on_startup=[database.connect],
    on_shutdown=[database.disconnect],
    middleware=[TenantMiddleware],
)

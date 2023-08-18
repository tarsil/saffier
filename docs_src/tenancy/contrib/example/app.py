from typing import List

from esmerald import Esmerald, Gateway, JSONResponse, get
from myapp.middleware import TenantMiddleware
from myapp.models import Product

import saffier

database = saffier.Database("<TOUR-CONNECTION-STRING>")
models = saffier.Registry(database=database)


@get("/products")
async def get_products() -> JSONResponse:
    """
    Returns the products associated to a tenant or
    all the "shared" products if tenant is None.

    The tenant was set in the `TenantMiddleware` which
    means that there is no need to use the `using` anymore.
    """
    products = await Product.query.all()
    products = [product.pk for product in products]
    return JSONResponse(products)


app = Esmerald(
    routes=[Gateway(handler=get_products)],
    on_startup=[database.connect],
    on_shutdown=[database.disconnect],
    middleware=[TenantMiddleware],
)

from typing import List

from esmerald import Esmerald, Gateway, get

import saffier

database = saffier.Database("<TOUR-CONNECTION-STRING>")
models = saffier.Registry(database=database)


@get("/products")
async def products() -> List[Product]:
    """
    Returns the products associated to a tenant or
    all the "shared" products if tenant is None.
    """
    products = await Product.query.all()
    return products


app = Esmerald(
    routes=[Gateway(handler=products)],
    on_startup=[database.connect],
    on_shutdown=[database.disconnect],
    middleware=[TenantMiddleware],
)

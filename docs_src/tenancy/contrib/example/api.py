from esmerald import JSONResponse, get
from myapp.models import Product


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

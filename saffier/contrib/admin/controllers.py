from __future__ import annotations

from typing import Any

from saffier.contrib.admin.mixins import AdminMixin, get_templates


async def admin_not_found(request: Any):
    try:
        from starlette.responses import HTMLResponse
    except ImportError:  # pragma: no cover
        return {"detail": "Not found"}

    return HTMLResponse("Admin page not found.", status_code=404)


__all__ = ["AdminMixin", "admin_not_found", "get_templates"]

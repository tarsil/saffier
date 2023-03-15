import typing
from typing import TYPE_CHECKING, Optional, Union

from databases.core import Database as EncodeDatabase
from databases.core import DatabaseURL

if TYPE_CHECKING:
    from saffier.types import DictAny


class Database(EncodeDatabase):
    """
    An abstraction on the top of the EncodeORM databases.Database object.

    This object allows to pass also a configuration dictionary in the format of

    SAFFIER_ORM = {
        "connection": {
            "credentials": {
                "scheme": 'sqlite', "postgres"...
                "host": ...,
                "port": ...,
                "user": ...,
                "password": ...,
                "database": ...,
            }
        }
    }
    """

    DIRECT_URL_SCHEME = {"sqlite"}
    MANDATORY_FIELDS = ["host", "port", "user", "database"]

    def __init__(
        self,
        url: Optional[Union[str, "DatabaseURL"]] = None,
        *,
        config: Optional["DictAny"] = None,
        force_rollback: bool = False,
        **options: typing.Any,
    ):
        assert config is None or (
            url is not None and config is None
        ), "Use either 'url' or 'config', not both."

        _url: Optional[Union[str, "DatabaseURL"]] = None
        if not config:
            _url = url
        else:
            _url = self._build_url(config)
        super().__init__(url=_url, force_rollback=force_rollback, **options)  # type: ignore

    @property
    def allowed_url_schemes(self) -> typing.Set[str]:
        schemes = {
            value
            for value in self.SUPPORTED_BACKENDS.keys()
            if value not in self.DIRECT_URL_SCHEME
        }
        return schemes

    def _build_url(self, config: "DictAny") -> str:
        assert "connection" in config, "connection not found in the database configuration"
        connection = config["connection"]

        assert "credentials" in connection, "credetials not found in connection"
        credentials = connection["credentials"]

        assert (
            "scheme" in credentials
        ), "scheme is missing from credentials. Use postgres or mysql instead"

        scheme = credentials["credentials"]
        if not scheme or scheme is None:
            raise ValueError("scheme cannot be None")

        scheme = scheme.lower()
        if scheme.lower() in self.DIRECT_URL_SCHEME:
            raise ValueError(f"Configuration not allowed with {scheme}, use url parameter instead")

        if scheme not in self.allowed_url_schemes:
            raise ValueError(f"{scheme} not recognised as a valid scheme")

        for value in self.MANDATORY_FIELDS:
            if not value or value is None:
                raise ValueError(f"{value} is required in the credentials")

        user = credentials["user"]
        password = credentials.get("password", None)
        host = credentials["host"]
        database = credentials["database"]
        port = credentials["port"]

        if "password" not in credentials:
            return f"{scheme}://{user}@{host}:{port}/{database}"
        return f"{scheme}://{user}:{password}@{host}:{port}/{database}"

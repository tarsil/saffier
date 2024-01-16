import uuid
from typing import Any, Dict, Type, Union, cast

from loguru import logger

import saffier
from saffier import settings
from saffier.contrib.multi_tenancy.exceptions import ModelSchemaError
from saffier.contrib.multi_tenancy.utils import create_tables
from saffier.core.db.models import Model
from saffier.core.db.models.utils import get_model
from saffier.exceptions import ObjectNotFound


class TenantMixin(saffier.Model):
    """
    Abstract table that acts as an entry-point for
    the tenants with saffier contrib.
    """

    id = saffier.BigIntegerField(primary_key=True)
    schema_name = saffier.CharField(max_length=63, unique=True, index=True)
    domain_url = saffier.URLField(null=True, default=settings.domain, max_length=2048)
    tenant_name = saffier.CharField(max_length=100, unique=True, null=False)
    tenant_uuid = saffier.UUIDField(default=uuid.uuid4, null=False)
    paid_until = saffier.DateField(null=True)
    on_trial = saffier.BooleanField(null=True)
    created_on = saffier.DateField(auto_now_add=True)

    # Default True, the schema will be automatically created and synched when it is saved.
    auto_create_schema: bool = getattr(settings, "auto_create_schema", True)
    """
    Set this flag to false on a parent class if you don't want the schema to be automatically
    generated.
    """
    auto_drop_schema: bool = getattr(settings, "auto_drop_schema", False)
    """
    Use with caution! Set this flag to true if you want the schema to be dropped if the
    tenant row is deleted from this table.
    """

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"{self.tenant_name} - {self.schema_name}"

    async def save(
        self: Any, force_save: bool = False, values: Dict[str, Any] = None, **kwargs: Any
    ) -> Type["TenantMixin"]:
        """
        Creates a tenant record and generates a schema in the database.

        When a schema is created, then generates the tables for that same schema
        from the tenant models.
        """
        fields = self.extract_db_fields()
        schema_name = fields.get("schema_name", None)

        if (
            not schema_name
            or schema_name.lower() == settings.tenant_schema_default.lower()
            or schema_name == self.meta.registry.db_schema
        ):
            current_schema = (
                settings.tenant_schema_default.lower()
                if not self.meta.registry.db_schema
                else self.meta.registry.db_schema
            )
            raise ModelSchemaError(
                "Can't update tenant outside it's own schema or the public schema. Current schema is '%s'"
                % current_schema
            )

        tenant: Type["Model"] = await super().save(force_save, values, **kwargs)
        try:
            await self.meta.registry.schema.create_schema(
                schema=tenant.schema_name, if_not_exists=True
            )
            await create_tables(
                self.meta.registry, self.meta.registry.tenant_models, tenant.schema_name
            )
        except Exception as e:
            message = f"Rolling back... {str(e)}"
            logger.error(message)
            await self.delete()
        return cast("Type[TenantMixin]", tenant)

    async def delete(self, force_drop: bool = False) -> None:
        """
        Validates the permissions for the schema before deleting it.
        """
        if self.schema_name == settings.tenant_schema_default:
            raise ValueError("Cannot drop public schema.")

        await self.meta.registry.schema.drop_schema(schema=self.schema_name, cascade=True, if_exists=True)  # type: ignore
        await super().delete()


class DomainMixin(saffier.Model):
    """
    All models that store the domains must use this class
    """

    id = saffier.BigIntegerField(primary_key=True)
    domain = saffier.CharField(max_length=253, unique=True, db_index=True)
    tenant = saffier.ForeignKey(
        settings.tenant_model, index=True, on_delete=saffier.CASCADE, related_name="domains"
    )
    is_primary = saffier.BooleanField(default=True, index=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return cast("str", self.domain)

    async def save(
        self: Any, force_save: bool = False, values: Dict[str, Any] = None, **kwargs: Any
    ) -> Type[Model]:
        async with self.meta.registry.database.transaction():
            domains = self.__class__.query.filter(tenant=self.tenant, is_priamry=True).exclude(
                id=self.pk
            )

            exists = await domains.exists()

            self.is_primary = self.is_primary or (not exists)
            if self.is_primary:
                await domains.update(is_primary=False)

            return await super().save(force_save, values, **kwargs)

    async def delete(self) -> None:
        tenant = await self.tenant.load()
        if (
            tenant.schema_name.lower() == settings.tenant_schema_default.lower()
            and self.domain == settings.domain_name
        ):
            raise ValueError("Cannot drop public domain.")
        return await super().delete()


class TenantUserMixin(saffier.Model):
    """
    Mapping between user and a client (tenant).
    """

    id = saffier.BigIntegerField(primary_key=True)
    user = saffier.ForeignKey(
        settings.auth_user_model,
        null=False,
        on_delete=saffier.CASCADE,
        related_name="tenant_user_users",
    )
    tenant = saffier.ForeignKey(
        settings.tenant_model,
        null=False,
        on_delete=saffier.CASCADE,
        related_name="tenant_users_tenant",
    )
    is_active = saffier.BooleanField(default=False)
    created_on = saffier.DateField(auto_now_add=True)

    class Meta:
        abstract = True

    def __str__(self) -> str:
        return f"User: {self.user.pk}, Tenant: {self.tenant}"

    @classmethod
    async def get_active_user_tenant(cls, user: Type["Model"]) -> Union[Type["Model"], None]:
        """
        Obtains the active user tenant.
        """
        try:
            tenant = await get_model(  # type: ignore
                registry=cls.meta.registry, model_name=cls.__name__
            ).query.get(user=user, is_active=True)
            await tenant.tenant.load()

        except ObjectNotFound:
            return None
        return cast("Type[Model]", tenant.tenant)

    async def save(self, *args: Any, **kwargs: Any) -> Type["TenantUserMixin"]:
        await super().save(*args, **kwargs)
        if self.is_active:
            await get_model(  # type: ignore
                registry=self.meta.registry, model_name=self.__class__.__name__
            ).query.filter(is_active=True, user=self.user).exclude(pk=self.pk).update(
                is_active=False
            )
        return cast("Type[TenantUserMixin]", self)

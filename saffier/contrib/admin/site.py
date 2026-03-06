from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any, cast

import orjson

import saffier
from saffier.contrib.pagination import NumberedPaginator, Page
from saffier.core.db import fields as saffier_fields

from .config import AdminConfig
from .exceptions import AdminModelNotFound, AdminValidationError


class AdminSite:
    """
    Python-native admin service for registry browsing and CRUD operations.
    """

    def __init__(
        self,
        *,
        registry: Any,
        config: AdminConfig | None = None,
        include_models: set[str] | None = None,
        exclude_models: set[str] | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or AdminConfig()
        self.include_models = include_models
        self.exclude_models = exclude_models or set()

    def get_registered_models(self) -> dict[str, type[saffier.Model]]:
        models: dict[str, type[saffier.Model]] = {}

        for name, model in self.registry.models.items():
            if name in self.registry.pattern_models:
                continue
            if getattr(model.meta, "abstract", False):
                continue
            if self.include_models is not None and name not in self.include_models:
                continue
            if name in self.exclude_models:
                continue
            models[name] = model

        for name, model in self.registry.reflected.items():
            if self.include_models is not None and name not in self.include_models:
                continue
            if name in self.exclude_models:
                continue
            models[name] = model

        return dict(sorted(models.items(), key=lambda item: item[0].lower()))

    def get_model(self, model_name: str) -> type[saffier.Model]:
        models = self.get_registered_models()
        if model_name not in models:
            raise AdminModelNotFound(f"Model {model_name!r} is not available in admin.")
        return models[model_name]

    async def get_model_counts(self) -> list[dict[str, Any]]:
        model_stats: list[dict[str, Any]] = []
        for name, model in self.get_registered_models().items():
            try:
                count = await model.query.count()
            except Exception:
                count = 0
            model_stats.append(
                {
                    "name": name,
                    "verbose": model.__name__,
                    "count": count,
                }
            )
        return model_stats

    def get_model_fields(
        self,
        model_name: str,
        *,
        for_write: bool = False,
    ) -> list[dict[str, Any]]:
        model = self.get_model(model_name)
        fields: list[dict[str, Any]] = []

        for name, field in model.fields.items():
            if isinstance(field, saffier_fields.ManyToManyField):
                continue

            validator = field.validator
            read_only = bool(validator.read_only)
            required = not field.null and not validator.has_default()
            spec = {
                "name": name,
                "type": field.__class__.__name__,
                "required": required,
                "read_only": read_only,
                "nullable": field.null,
                "primary_key": field.primary_key,
                "default": validator.get_default_value() if validator.has_default() else None,
            }
            if for_write and read_only and not field.primary_key:
                continue
            if for_write and field.primary_key and field.autoincrement:
                continue
            fields.append(spec)

        return fields

    def get_model_schema(self, model_name: str) -> dict[str, Any]:
        model = self.get_model(model_name)
        return {
            "model": model_name,
            "pk_name": model.pkname,
            "fields": self.get_model_fields(model_name),
        }

    def create_object_pk(self, instance: saffier.Model) -> str:
        pk_dict = {instance.pkname: getattr(instance, instance.pkname)}
        return urlsafe_b64encode(orjson.dumps(pk_dict, default=str)).decode()

    def parse_object_pk(self, encoded_pk: str) -> dict[str, Any]:
        try:
            result = orjson.loads(urlsafe_b64decode(encoded_pk))
        except Exception as exc:  # noqa: BLE001
            raise AdminValidationError({"pk": "Invalid object primary key payload."}) from exc

        if not isinstance(result, dict):
            raise AdminValidationError({"pk": "Invalid object primary key payload."})
        return result

    def _build_search_clause(self, model: type[saffier.Model], term: str) -> saffier.Q | None:
        term = term.strip()
        if not term:
            return None

        lookup_fields = [
            name
            for name, field in model.fields.items()
            if isinstance(field, (saffier_fields.CharField, saffier_fields.TextField))
        ]
        if not lookup_fields:
            return None

        clause: saffier.Q | None = None
        for field in lookup_fields:
            item = saffier.Q(**{f"{field}__icontains": term})
            clause = item if clause is None else clause | item
        return clause

    async def list_objects(
        self,
        model_name: str,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        order_by: str | None = None,
    ) -> Page:
        model = self.get_model(model_name)
        queryset = model.query.order_by(order_by or model.pkname)
        clause = self._build_search_clause(model, search)
        if clause is not None:
            queryset = queryset.filter(clause)

        paginator = NumberedPaginator(queryset, page_size=page_size)
        return await paginator.get_page(page)

    async def get_object(self, model_name: str, encoded_pk: str) -> saffier.Model:
        model = self.get_model(model_name)
        pk_payload = self.parse_object_pk(encoded_pk)
        return await model.query.get(**pk_payload)

    def _coerce_payload(
        self,
        model: type[saffier.Model],
        payload: dict[str, Any],
        *,
        partial: bool = False,
    ) -> dict[str, Any]:
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}

        for key, raw_value in payload.items():
            field = model.fields.get(key)
            if field is None:
                errors[key] = "Unknown field."
                continue
            if isinstance(field, saffier_fields.ManyToManyField):
                continue
            if field.validator.read_only and not (field.primary_key and not field.autoincrement):
                continue

            value = None if raw_value == "" and field.null else raw_value
            try:
                values[key] = field.validator.check(value)
            except Exception as exc:  # noqa: BLE001
                errors[key] = str(exc)

        if not partial:
            for field_name, field in model.fields.items():
                if field_name in values:
                    continue
                if isinstance(field, saffier_fields.ManyToManyField):
                    continue
                if field.primary_key and field.autoincrement:
                    continue
                if field.validator.read_only and not field.primary_key:
                    continue
                if field.validator.has_default():
                    values[field_name] = field.validator.get_default_value()
                    continue
                if field.null:
                    values[field_name] = None
                    continue
                errors[field_name] = "This field is required."

        if errors:
            raise AdminValidationError(errors)
        return values

    def form_to_payload(self, form_data: Any) -> dict[str, Any]:
        editor_payload = form_data.get("editor_data")
        if editor_payload:
            try:
                parsed = orjson.loads(editor_payload)
            except Exception as exc:  # noqa: BLE001
                raise AdminValidationError({"editor_data": "Invalid JSON payload."}) from exc
            if not isinstance(parsed, dict):
                raise AdminValidationError({"editor_data": "Payload must be a JSON object."})
            return dict(parsed)

        payload = {}
        for key, value in form_data.multi_items():
            if key.startswith("_"):
                continue
            payload[key] = value
        return payload

    async def create_object(self, model_name: str, payload: dict[str, Any]) -> saffier.Model:
        model = self.get_model(model_name)
        values = self._coerce_payload(model, payload)
        return await model.query.create(**values)

    async def update_object(
        self,
        model_name: str,
        encoded_pk: str,
        payload: dict[str, Any],
    ) -> saffier.Model:
        model = self.get_model(model_name)
        values = self._coerce_payload(model, payload, partial=True)
        instance = await self.get_object(model_name, encoded_pk)
        if values:
            await instance.update(**values)
        return cast(saffier.Model, instance)

    async def delete_object(self, model_name: str, encoded_pk: str) -> int:
        instance = await self.get_object(model_name, encoded_pk)
        return await instance.delete()

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Any, cast

import orjson

import saffier
from saffier.contrib.pagination import NumberedPaginator, Page
from saffier.core.db import fields as saffier_fields
from saffier.exceptions import ValidationError

from .config import AdminConfig
from .exceptions import AdminModelNotFound, AdminValidationError


class AdminSite:
    """Registry-backed admin service for browsing and editing Saffier models.

    The admin site exposes lightweight schema inspection, listing, search, CRUD,
    and pagination helpers that power the built-in admin UI.
    """

    def __init__(
        self,
        *,
        registry: Any,
        config: AdminConfig | None = None,
        include_models: set[str] | None = None,
        exclude_models: set[str] | None = None,
    ) -> None:
        """Create an admin service bound to a Saffier registry.

        Args:
            registry: Saffier registry whose models should be exposed.
            config: Optional admin configuration. When omitted, a default
                ``AdminConfig`` is created.
            include_models: Optional registry-name allowlist applied after the
                registry's admin visibility rules.
            exclude_models: Optional registry-name denylist applied after
                inclusion filtering.
        """
        self.registry = registry
        self.config = config or AdminConfig()
        self.include_models = include_models
        self.exclude_models = exclude_models or set()

    def get_registered_models(self) -> dict[str, type[saffier.Model]]:
        """Return the models visible through the built-in admin.

        The registry owns the canonical admin membership set. Models are added
        to that set during registration unless ``Meta.in_admin`` is explicitly
        ``False``. ``AdminSite`` then applies its optional include/exclude
        filters on top, which keeps application-specific admin instances cheap
        without changing the registry-wide public surface.

        Returns:
            dict[str, type[saffier.Model]]: Sorted mapping of admin-visible
            model names to Saffier model classes.
        """
        models: dict[str, type[saffier.Model]] = {}
        admin_models = getattr(self.registry, "admin_models", None)

        for name, model in self.registry.models.items():
            if (
                admin_models is not None
                and name not in admin_models
                and (self.include_models is None or name not in self.include_models)
            ):
                continue
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
            if (
                admin_models is not None
                and name not in admin_models
                and (self.include_models is None or name not in self.include_models)
            ):
                continue
            if self.include_models is not None and name not in self.include_models:
                continue
            if name in self.exclude_models:
                continue
            models[name] = model

        return dict(sorted(models.items(), key=lambda item: item[0].lower()))

    def can_create_model(self, model_name: str) -> bool:
        """Return whether the admin may create objects for one model.

        ``Meta.no_admin_create`` keeps infrastructure models browsable while
        preventing direct creation. Saffier applies the flag in the service
        layer so both UI routes and programmatic admin calls share the same
        protection.

        Args:
            model_name: Admin-visible model name.

        Returns:
            bool: ``True`` when the create workflow should be available.
        """
        model = self.get_model(model_name)
        return getattr(model.meta, "no_admin_create", None) is not True

    def get_model(self, model_name: str) -> type[saffier.Model]:
        """Resolve one admin-visible model by its registered name.

        The admin UI always works with registry names instead of importing model
        classes from templates or controllers. Centralizing lookup here keeps
        include/exclude filters, reflected models, and ``Meta.in_admin`` rules
        consistent for every route and service method.

        Args:
            model_name: Name used by the registry and admin URLs.

        Returns:
            type[saffier.Model]: Concrete Saffier model class.

        Raises:
            AdminModelNotFound: If the model is not registered for this admin
            site instance.
        """
        models = self.get_registered_models()
        if model_name not in models:
            raise AdminModelNotFound(f"Model {model_name!r} is not available in admin.")
        return models[model_name]

    async def get_model_counts(self) -> list[dict[str, Any]]:
        """Count records for each model currently visible in admin.

        Count failures are intentionally isolated per model. Admin dashboards
        should remain reachable while one table is unavailable, reflected
        metadata is incomplete, or a database backend rejects a particular
        count query.

        Returns:
            list[dict[str, Any]]: Ordered model summary dictionaries containing
            the registry name, display name, record count, and creation flag.
        """
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
                    "no_admin_create": not self.can_create_model(name),
                }
            )
        return model_stats

    def get_model_fields(
        self,
        model_name: str,
        *,
        for_write: bool = False,
    ) -> list[dict[str, Any]]:
        """Describe model fields for templates and JSON responses.

        The field list is derived from Saffier field declarations rather than
        SQLAlchemy columns so virtual/read-only flags and admin marshalling
        choices are represented consistently. Many-to-many fields are excluded
        from this lightweight table view because they require dedicated
        relation editing UI.

        Args:
            model_name: Registry name for the model being described.
            for_write: When true, omit fields that should not be posted by
                create/edit workflows.

        Returns:
            list[dict[str, Any]]: Field descriptors sorted in model declaration
            order.
        """
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
        """Return the public admin schema metadata for one model.

        This schema powers the JSON endpoint used by tooling and smoke tests.
        Rich create/edit pages use ``get_model_editor_schema`` because
        JSONEditor expects the model marshall JSON schema, while this method
        intentionally exposes a compact Saffier-specific shape.

        Args:
            model_name: Registry name for the model being described.

        Returns:
            dict[str, Any]: Admin schema metadata including primary-key fields,
            create permission, and field descriptors.
        """
        model = self.get_model(model_name)
        return {
            "model": model_name,
            "pk_name": model.pkname,
            "pk_names": list(model.pknames),
            "can_create": self.can_create_model(model_name),
            "fields": self.get_model_fields(model_name),
        }

    def get_model_editor_schema(self, model_name: str, *, phase: str) -> dict[str, Any]:
        """Return a JSONEditor-compatible schema for create or edit forms.

        Saffier models expose admin marshall classes that already know which
        fields belong in a given admin phase. This method delegates to that
        model-owned schema path so the HTML editor stays aligned with custom
        ``get_admin_marshall_config`` overrides and future field-level schema
        improvements.

        Args:
            model_name: Registry name for the model being edited.
            phase: Admin marshalling phase. ``"create"`` includes create-time
                fields, while ``"update"`` excludes read-only and
                auto-generated fields.

        Returns:
            dict[str, Any]: JSON schema suitable for ``@json-editor/json-editor``.
        """
        model = self.get_model(model_name)
        return model.model_json_schema(
            mode="validation",
            phase=phase,
            include_callable_defaults=phase == "create",
        )

    def create_object_pk(self, instance: saffier.Model) -> str:
        """Encode a model instance primary key for admin URLs.

        Composite and scalar primary keys are normalized to the same dictionary
        form before encoding. The JSON payload is URL-safe base64 so admin URLs
        can round-trip natural keys without relying on database-specific string
        formatting.

        Args:
            instance: Persisted Saffier model instance.

        Returns:
            str: URL-safe encoded primary-key payload.
        """
        pk_value = instance.pk
        pk_dict = (
            pk_value
            if isinstance(pk_value, dict)
            else {instance.pkname: getattr(instance, instance.pkname)}
        )
        return urlsafe_b64encode(orjson.dumps(pk_dict, default=str)).decode()

    def parse_object_pk(self, encoded_pk: str) -> dict[str, Any]:
        """Decode an admin URL primary-key payload.

        Args:
            encoded_pk: URL-safe base64 payload previously produced by
                ``create_object_pk``.

        Returns:
            dict[str, Any]: Primary-key lookup values.

        Raises:
            AdminValidationError: If the payload cannot be decoded or does not
            contain a JSON object.
        """
        try:
            result = orjson.loads(urlsafe_b64decode(encoded_pk))
        except Exception as exc:  # noqa: BLE001
            raise AdminValidationError({"pk": "Invalid object primary key payload."}) from exc

        if not isinstance(result, dict):
            raise AdminValidationError({"pk": "Invalid object primary key payload."})
        return result

    def _build_search_clause(self, model: type[saffier.Model], term: str) -> saffier.Q | None:
        """Build a text-search clause for simple admin list filtering.

        The built-in admin search intentionally searches only character-like
        fields. That keeps the default behavior cheap and predictable across SQL
        dialects while still covering the common "find by name/title/email"
        workflow.

        Args:
            model: Saffier model class being listed.
            term: User-entered search term.

        Returns:
            saffier.Q | None: Combined OR clause, or ``None`` when no searchable
            text fields exist or the term is empty.
        """
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

    def _build_list_queryset(
        self,
        model_name: str,
        *,
        search: str = "",
        order_by: str | None = None,
    ) -> Any:
        """Construct the queryset used by admin list views.

        List routes, count calculations, and tests should all apply ordering and
        search in the same way. Returning the queryset from one private helper
        avoids route-level drift while still leaving pagination policy to the
        caller.

        Args:
            model_name: Registry name for the model being listed.
            search: Optional text search term.
            order_by: Optional explicit Saffier ordering expression.

        Returns:
            Any: Saffier queryset ready to paginate or count.
        """
        model = self.get_model(model_name)
        queryset = (
            model.query.order_by(order_by)
            if order_by is not None
            else model.query.order_by(*model.pknames)
        )
        clause = self._build_search_clause(model, search)
        if clause is not None:
            queryset = queryset.filter(clause)
        return queryset

    async def list_objects(
        self,
        model_name: str,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        order_by: str | None = None,
    ) -> Page:
        """Return one numbered page of admin objects.

        Args:
            model_name: Registry name for the model being listed.
            page: One-based page number.
            page_size: Maximum records to include in the page.
            search: Optional text search term.
            order_by: Optional explicit ordering expression.

        Returns:
            Page: Saffier numbered page object.
        """
        queryset = self._build_list_queryset(model_name, search=search, order_by=order_by)
        paginator = NumberedPaginator(queryset, page_size=page_size)
        return await paginator.get_page(page)

    async def list_objects_with_totals(
        self,
        model_name: str,
        *,
        page: int = 1,
        page_size: int = 25,
        search: str = "",
        order_by: str | None = None,
    ) -> tuple[Page, int, int]:
        """Return a page plus total counts for the richer admin UI.

        The generic paginator intentionally keeps ``Page`` small. The admin
        table, however, needs total records and total pages to render its
        pagination controls. This method calculates those values from the same
        filtered queryset used for the page so the numbers match what the
        operator is seeing.

        Args:
            model_name: Registry name for the model being listed.
            page: One-based page number.
            page_size: Maximum records to include in the page.
            search: Optional text search term.
            order_by: Optional explicit ordering expression.

        Returns:
            tuple[Page, int, int]: Page object, total matching records, and
            total page count.
        """
        queryset = self._build_list_queryset(model_name, search=search, order_by=order_by)
        paginator = NumberedPaginator(queryset, page_size=page_size)
        page_obj = await paginator.get_page(page)
        total_records = await paginator.get_total()
        total_pages = await paginator.get_amount_pages()
        return page_obj, total_records, max(total_pages, 1)

    def get_object_display_values(self, instance: saffier.Model) -> dict[str, Any]:
        """Serialize an instance for admin detail rendering.

        Admin detail pages should show the same field-level representation as
        Saffier model dumps without exposing private instance state. Keeping the
        conversion in the service layer makes templates simpler and gives future
        relation/file rendering one place to grow.

        Args:
            instance: Saffier model instance being displayed.

        Returns:
            dict[str, Any]: Field-value mapping safe for templates.
        """
        return instance.model_dump()

    def get_object_editor_values(self, instance: saffier.Model) -> dict[str, Any]:
        """Serialize an instance as JSONEditor start values.

        The edit page uses JSONEditor, which expects a plain JSON-compatible
        object. ``model_dump`` supplies the public field mapping, while the
        final JSON encoding step handles database-specific values such as dates
        through ``orjson``'s default string conversion.

        Args:
            instance: Saffier model instance being edited.

        Returns:
            dict[str, Any]: Initial form values keyed by model field name.
        """
        return instance.model_dump()

    async def get_object(self, model_name: str, encoded_pk: str) -> saffier.Model:
        """Load one model instance from an encoded admin primary key.

        Args:
            model_name: Registry name for the model being loaded.
            encoded_pk: URL-safe primary-key payload from an admin URL.

        Returns:
            saffier.Model: Loaded model instance.
        """
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
        """Validate and coerce raw admin payload values for one model.

        Field validators remain the source of truth for type conversion. This
        helper filters unknown, read-only, and many-to-many fields, fills
        defaults for create operations, and collects validation errors into the
        admin-specific exception shape consumed by templates and API callers.

        Args:
            model: Saffier model class receiving the payload.
            payload: Raw values keyed by model field name.
            partial: Whether missing fields are allowed, as they are during
                updates.

        Returns:
            dict[str, Any]: Coerced values safe to pass to model create/update
            methods.

        Raises:
            AdminValidationError: If one or more fields fail validation or a
            required create field is missing.
        """
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

    def _build_save_marshall(
        self,
        model: type[saffier.Model],
        payload: dict[str, Any],
        *,
        instance: saffier.Model | None = None,
    ) -> Any:
        """Build the model-owned admin marshall for a create or update write.

        The admin service still owns request-level concerns such as rejecting
        unknown fields and converting empty form strings to ``None`` for
        nullable model fields. Model-specific projection and validation,
        however, belong to ``get_admin_marshall_for_save()`` so applications
        that customize admin marshalling affect both schemas and writes.

        Args:
            model: Saffier model class being created or updated.
            payload: Raw user payload keyed by model field name.
            instance: Existing instance for update operations. ``None`` means a
                create operation is being prepared.

        Returns:
            Any: Admin marshall instance ready to save.

        Raises:
            AdminValidationError: If a field is unknown, not writable in the
            current admin phase, or rejected by the model marshall.
        """
        phase = "update" if instance is not None else "create"
        marshall_class = model.get_admin_marshall_class(phase=phase, for_schema=False)
        writable_fields = set(marshall_class.model_fields)
        errors: dict[str, str] = {}
        values: dict[str, Any] = {}

        for key, raw_value in payload.items():
            field = model.fields.get(key)
            if field is None:
                errors[key] = "Unknown field."
                continue
            if isinstance(field, saffier_fields.ManyToManyField):
                continue
            if key not in writable_fields:
                errors[key] = "Field is not writable."
                continue
            values[key] = None if raw_value == "" and field.null else raw_value

        if errors:
            raise AdminValidationError(errors)

        try:
            return model.get_admin_marshall_for_save(instance, **values)
        except ValidationError as exc:
            validation_errors: dict[str, str] = {}
            for message in exc.messages():
                key = str(message.index[0]) if message.index else "__all__"
                validation_errors[key] = message.text
            raise AdminValidationError(validation_errors) from exc
        except Exception as exc:
            raise AdminValidationError({"__all__": str(exc)}) from exc

    def form_to_payload(self, form_data: Any) -> dict[str, Any]:
        """Convert submitted admin form data into a model payload.

        JSONEditor-backed pages submit a single ``editor_data`` JSON object. The
        fallback path handles plain form submissions by reading Lilya's
        ``multi_items`` API and ignoring private control fields.

        Args:
            form_data: Lilya form object or compatible test double.

        Returns:
            dict[str, Any]: Payload keyed by model field name.

        Raises:
            AdminValidationError: If ``editor_data`` is malformed or does not
            decode to a JSON object.
        """
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
        """Create one model instance through the admin service.

        Creation is refused when ``Meta.no_admin_create`` is true. Keeping this
        check in the service layer prevents callers from bypassing the UI route
        and gives tests a single behavior to verify for both ASGI and direct
        admin usage.

        Args:
            model_name: Admin-visible model name.
            payload: Raw user payload keyed by Saffier field name.

        Returns:
            saffier.Model: Newly persisted model instance.

        Raises:
            AdminValidationError: If creation is disabled or payload coercion
            fails.
        """
        model = self.get_model(model_name)
        if not self.can_create_model(model_name):
            raise AdminValidationError({"model": "Creation is disabled for this model."})
        marshall = self._build_save_marshall(model, payload)
        await marshall.save()
        return cast(saffier.Model, marshall.instance)

    async def update_object(
        self,
        model_name: str,
        encoded_pk: str,
        payload: dict[str, Any],
    ) -> saffier.Model:
        """Update one model instance through the admin service.

        Args:
            model_name: Registry name for the model being updated.
            encoded_pk: URL-safe primary-key payload for the target instance.
            payload: Raw user payload keyed by Saffier field name.

        Returns:
            saffier.Model: Updated model instance.

        Raises:
            AdminValidationError: If payload coercion fails.
        """
        model = self.get_model(model_name)
        instance = await self.get_object(model_name, encoded_pk)
        if not payload:
            return cast(saffier.Model, instance)
        marshall = self._build_save_marshall(model, payload, instance=instance)
        await marshall.save()
        return cast(saffier.Model, marshall.instance)

    async def delete_object(self, model_name: str, encoded_pk: str) -> int:
        """Delete one model instance through the admin service.

        Args:
            model_name: Registry name for the model being deleted.
            encoded_pk: URL-safe primary-key payload for the target instance.

        Returns:
            int: Number of rows deleted by Saffier.
        """
        instance = await self.get_object(model_name, encoded_pk)
        return await instance.delete()

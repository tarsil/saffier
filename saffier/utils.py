from saffier.fields import CharField, DateField, DateTimeField, TextField
from saffier.types import DictAny


class ModelUtil:
    """
    Utils used by the Registry
    """

    def _update_auto_now_fields(values: DictAny, fields: DictAny) -> DictAny:
        """
        Updates the auto fields
        """
        for k, v in fields.items():
            if isinstance(v, (DateField, DateField)) and v.auto_now:
                values[k] = v.validator.get_default_value()
        return values

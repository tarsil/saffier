import inspect
import typing

from sqlalchemy.orm import Mapped, relationship


class DeclarativeMixin:
    """Expose SQLAlchemy declarative models derived from a Saffier model.

    This mixin is the bridge used by integrations that need a classic
    SQLAlchemy ORM class bound to the same table metadata and simple foreign-key
    relationships already declared on the Saffier model.
    """

    @classmethod
    def declarative(cls) -> typing.Any:
        """Return the generated SQLAlchemy declarative model class.

        Returns:
            typing.Any: Declarative SQLAlchemy model created from the Saffier
            model definition.
        """
        return cls.generate_model_declarative()

    @classmethod
    def generate_model_declarative(cls) -> typing.Any:
        """Transform the Saffier table into a SQLAlchemy declarative model.

        Returns:
            typing.Any: Declarative model class bound to the same SQLAlchemy
            table.
        """
        Base = cls.meta.registry.declarative_base

        # Build the original table
        fields = {"__table__": cls.table}

        # Generate base
        model_table = type(cls.__name__, (Base,), fields)

        # Make sure if there are foreignkeys, builds the relationships
        for column in cls.table.columns:
            if not column.foreign_keys:
                continue

            # Maps the relationships with the foreign keys and related names
            field = cls.fields.get(column.name)
            to = field.to.__name__ if inspect.isclass(field.to) else field.to
            mapped_model: Mapped[to] = relationship(to)  # type: ignore

            # Adds to the current model
            model_table.__mapper__.add_property(f"{column.name}_relation", mapped_model)

        return model_table

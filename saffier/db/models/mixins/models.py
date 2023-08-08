import typing

import sqlalchemy
from sqlalchemy.orm import Mapped, relationship

import saffier
from saffier.conf import settings
from saffier.core.utils import ModelUtil
from saffier.db.datastructures import Index, UniqueConstraint

if typing.TYPE_CHECKING:
    from saffier.db.models.base import Model


class ModelBuilder(ModelUtil):
    """
    All the operations performed by the model added to
    a common mixin.
    """

    @property
    def pk(self) -> typing.Any:
        return getattr(self, self.pkname)

    @pk.setter
    def pk(self, value: typing.Any) -> typing.Any:
        setattr(self, self.pkname, value)

    @property
    def raw_query(self) -> typing.Any:
        return getattr(self, self._raw_query)  # type: ignore

    @raw_query.setter
    def raw_query(self, value: typing.Any) -> typing.Any:
        setattr(self, self.raw_query, value)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}: {self}>"

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.pkname}={self.pk})"

    @property
    def table(self) -> sqlalchemy.Table:
        return self.__class__.table

    @classmethod
    def build_table(cls) -> typing.Any:
        """
        Performs the operation of building the core SQLAlchemy Table object.
        Builds the constrainst, indexes, columns and metadata based on the
        provided Meta class object.
        """
        tablename = cls._meta.tablename
        metadata = cls._meta.registry._metadata  # type: ignore
        unique_together = cls._meta.unique_together
        index_constraints = cls._meta.indexes

        columns = []
        for name, field in cls.fields.items():
            columns.append(field.get_column(name))

        # Handle the uniqueness together
        uniques = []
        for field in unique_together or []:
            unique_constraint = cls._get_unique_constraints(field)
            uniques.append(unique_constraint)

        # Handle the indexes
        indexes = []
        for field in index_constraints or []:
            index = cls._get_indexes(field)
            indexes.append(index)

        return sqlalchemy.Table(
            tablename, metadata, *columns, *uniques, *indexes, extend_existing=True
        )

    @classmethod
    def _get_unique_constraints(
        cls, columns: typing.Sequence
    ) -> typing.Optional[sqlalchemy.UniqueConstraint]:
        """
        Returns the unique constraints for the model.

        The columns must be a a list, tuple of strings or a UniqueConstraint object.
        """
        if isinstance(columns, str):
            return sqlalchemy.UniqueConstraint(columns)
        elif isinstance(columns, UniqueConstraint):
            return sqlalchemy.UniqueConstraint(*columns.fields)
        return sqlalchemy.UniqueConstraint(*columns)

    @classmethod
    def _get_indexes(cls, index: Index) -> typing.Optional[sqlalchemy.Index]:
        """
        Creates the index based on the Index fields
        """
        return sqlalchemy.Index(index.name, *index.fields)

    def update_from_dict(self, dict_values: typing.Dict[str, typing.Any]) -> "Model":
        """Updates the current model object with the new fields"""
        for key, value in dict_values.items():
            setattr(self, key, value)
        return self

    def extract_db_fields(self):
        """
        Extacts all the db fields and excludes the related_names since those
        are simply relations.
        """
        related_names = self._meta.related_names
        return {k: v for k, v in self.__dict__.items() if k not in related_names}

    def __setattr__(self, key: typing.Any, value: typing.Any) -> typing.Any:
        if key in self.fields:
            # Setting a relationship to a raw pk value should set a
            # fully-fledged relationship instance, with just the pk loaded.
            field = self.fields[key]

            if isinstance(field, saffier.ManyToManyField):
                value = getattr(self, settings.many_to_many_relation.format(key=key))
            else:
                value = self.fields[key].expand_relationship(value)

        super().__setattr__(key, value)

    def __eq__(self, other: typing.Any) -> bool:
        if self.__class__ != other.__class__:
            return False
        for key in self.fields.keys():
            if getattr(self, key, None) != getattr(other, key, None):
                return False
        return True


class DeclarativeMixin:
    """
    Exposes all the declarative operations
    for a given Saffier model object.
    """

    @classmethod
    def declarative(cls) -> typing.Any:
        return cls.generate_model_declarative()

    @classmethod
    def generate_model_declarative(cls) -> typing.Any:
        """
        Transforms a core Saffier table into a Declarative model table.
        """
        Base = cls._meta.registry.declarative_base

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
            mapped_model: Mapped[field.to.__name__] = relationship(field.to.__name__)

            # Adds to the current model
            model_table.__mapper__.add_property(f"{column.name}_relation", mapped_model)

        return model_table

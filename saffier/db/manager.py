from saffier.db.queryset import QuerySet


class Manager(QuerySet):
    """
    Base Manager for the Saffier Models.
    To create a custom manager, the best approach is to inherit from the ModelManager.

    Example:
        from saffier.managers import ModelManager
        from saffier.models import Model


        class MyCustomManager(ModelManager):
            ...


        class MyOtherManager(ModelManager):
            ...


        class MyModel(saffier.Model):
            query = MyCustomManager()
            active = MyOtherManager()

            ...
    """

    # def __init__(self, model_class=None):
    #     self.model_class = None

    # def __get__(self, instance, owner):
    #     return self.__class__(model_class=owner)

    # def get_queryset(self) -> "QuerySet":
    #     return QuerySet(model_class=self.model_class)

    # def __getattr__(self, item):
    # return getattr(self.get_queryset(), item)

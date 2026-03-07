from saffier.core.datastructures import ArbitraryHashableBaseModel, HashableBaseModel


def test_hashable_base_model_hashes_mutable_values():
    item = HashableBaseModel(name="a", tags=["x", "y"], flags={"one"})
    hashed = hash(item)
    assert isinstance(hashed, int)


def test_arbitrary_hashable_is_compatible_alias():
    item = ArbitraryHashableBaseModel(value=1)
    assert isinstance(item, HashableBaseModel)
    assert item.value == 1

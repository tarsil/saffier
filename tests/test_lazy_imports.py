import saffier


def test_lazy_imports():
    missing = saffier.monkay.find_missing(
        all_var=saffier.__all__,
        search_pathes=[
            ".core.connection",
            ".core.db.models",
            ".core.db.fields",
            ".core.db.constants",
        ],
    )
    missing.pop("saffier.core.db.fields.BaseField", None)
    missing.pop("saffier.core.db.fields.BaseFieldType", None)
    assert not missing

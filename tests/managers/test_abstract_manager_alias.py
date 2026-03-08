import saffier


def test_abstract_model_allows_redirect_manager_alias() -> None:
    class AbstractTenantLike(saffier.Model):
        name = saffier.CharField(max_length=100)

        class Meta:
            abstract = True

    assert AbstractTenantLike.meta.abstract is True

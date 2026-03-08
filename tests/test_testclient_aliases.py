from saffier.testclient import DatabaseTestClient, SaffierTestClient


def test_saffier_testclient_aliases() -> None:
    assert issubclass(SaffierTestClient, DatabaseTestClient)
    assert SaffierTestClient is DatabaseTestClient

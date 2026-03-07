from ravyn import Ravyn

from saffier import Database, Registry

database = Database("sqlite:///db.sqlite")
models = Registry(database=database)


app = Ravyn(
    routes=[...],
    on_startup=[database.connect],
    on_shutdown=[database.disconnect],
)

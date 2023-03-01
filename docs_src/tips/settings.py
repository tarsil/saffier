"""
Generated by 'esmerald-admin createproject'
"""
from typing import Optional, Tuple

from esmerald.conf.enums import EnvironmentType
from esmerald.conf.global_settings import EsmeraldAPISettings
from saffier import Database, Registry


class AppSettings(EsmeraldAPISettings):
    app_name: str = "My application in production mode."
    environment: Optional[str] = EnvironmentType.PRODUCTION
    secret_key: str = "esmerald-insecure-h35r*b9$+hw-x2hnt5c)vva=!zn$*a7#"  # auto generated

    @property
    def db_connection(self) -> Tuple[Database, Registry]:
        database = Database("postgresql+asyncpg://user:pass@localhost:5432/my_database")
        return database, Registry(database=database)

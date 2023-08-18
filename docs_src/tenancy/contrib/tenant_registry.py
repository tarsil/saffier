import saffier
from saffier.contrib.multi_tenancy import TenantRegistry

database = saffier.Database("<YOUR-CONNECTION-STRING>")
registry = TenantRegistry(database=database)

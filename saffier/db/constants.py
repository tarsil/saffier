ITERATOR_CHUNK_SIZE = 100
ORDER_DIR = {
    "ASC": ("ASC", "DESC"),
    "DESC": ("DESC", "ASC"),
}
MAX_GET_RESULTS = 21

FILTER_OPERATORS = {
    "exact": "__eq__",
    "iexact": "ilike",
    "contains": "like",
    "icontains": "ilike",
    "in": "in_",
    "gt": "__gt__",
    "gte": "__ge__",
    "lt": "__lt__",
    "lte": "__le__",
}

CASCADE = "CASCADE"
RESTRICT = "RESTRICT"
SET_NULL = "SET NULL"
REPR_OUTPUT_SIZE = 20
SAFFIER_PICKLE_KEY = "saffier-version"

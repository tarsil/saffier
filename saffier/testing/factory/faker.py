from __future__ import annotations

import datetime
import random
import string
import uuid
from typing import Any


class _FallbackFaker:
    """
    Lightweight faker fallback used when the optional `faker` package is unavailable.
    """

    def pyint(self, *, min_value: int = 0, max_value: int = 9999) -> int:
        return random.randint(min_value, max_value)

    def random_int(self, *, min: int = 0, max: int = 9999) -> int:
        return random.randint(min, max)

    def pyfloat(
        self,
        *,
        left_digits: int = 2,
        right_digits: int = 2,
        positive: bool = False,
        min_value: float | None = None,
        max_value: float | None = None,
    ) -> float:
        if min_value is not None and max_value is not None:
            value = random.uniform(min_value, max_value)
        else:
            max_abs = float(10 ** max(left_digits, 1))
            value = random.uniform(0.0 if positive else -max_abs, max_abs)
        return round(value, right_digits)

    def pybool(self, probability: int | None = None) -> bool:
        if probability is None:
            return bool(random.getrandbits(1))
        probability = max(0, min(100, int(probability)))
        return random.randint(1, 100) <= probability

    def word(self) -> str:
        return "".join(random.choices(string.ascii_lowercase, k=8))

    def sentence(self) -> str:
        return f"{self.word()} {self.word()} {self.word()}."

    def date_object(self) -> datetime.date:
        return datetime.date.today()

    def date_time(self) -> datetime.datetime:
        return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

    def time_object(self) -> datetime.time:
        return datetime.datetime.now(datetime.timezone.utc).time().replace(microsecond=0)

    def email(self) -> str:
        return f"{self.word()}@example.com"

    def url(self) -> str:
        return f"https://{self.word()}.example.com"

    def ipv4(self) -> str:
        return ".".join(str(random.randint(1, 254)) for _ in range(4))

    def password(self) -> str:
        return "".join(random.choices(string.ascii_letters + string.digits, k=16))

    def binary(self, *, length: int = 8) -> bytes:
        return bytes(random.getrandbits(8) for _ in range(length))

    def uuid4(self) -> str:
        return str(uuid.uuid4())

    def name(self) -> str:
        return f"{self.word().title()} {self.word().title()}"

    def language_code(self) -> str:
        return random.choice(["en", "de", "fr", "es", "pt"])

    def random_element(self, *, elements: list[Any]) -> Any:
        return random.choice(elements)


def make_faker() -> Any:
    try:
        from faker import Faker
    except ImportError:
        return _FallbackFaker()
    return Faker()

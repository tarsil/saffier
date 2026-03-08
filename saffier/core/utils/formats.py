"""Low-level value parsers used by Saffier field validators."""

import datetime
import ipaddress
import re
import typing
import uuid
from urllib.parse import urlparse

from saffier.exceptions import ValidationError

DATE_REGEX = re.compile(r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})$")

TIME_REGEX = re.compile(
    r"(?P<hour>\d{1,2}):(?P<minute>\d{1,2})"
    r"(?::(?P<second>\d{1,2})(?:\.(?P<microsecond>\d{1,6})\d{0,6})?)?"
)

DATETIME_REGEX = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{1,2})-(?P<day>\d{1,2})"
    r"[T ](?P<hour>\d{1,2}):(?P<minute>\d{1,2})"
    r"(?::(?P<second>\d{1,2})(?:\.(?P<microsecond>\d{1,6})\d{0,6})?)?"
    r"(?P<tzinfo>Z|[+-]\d{2}(?::?\d{2})?)?$"
)

UUID_REGEX = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")

EMAIL_REGEX = re.compile(
    r"(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*"
    r'|^"([\001-\010\013\014\016-\037!#-\[\]-\177]|\\[\001-\011\013\014\016-\177])*'
    r")@(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}(?<!-)\.?$",
    re.IGNORECASE,
)

IPV4_REGEX = re.compile(
    r"(?:0|25[0-5]|2[0-4]\d|1\d?\d?|[1-9]\d?)" r"(?:\.(?:0|25[0-5]|2[0-4]\d|1\d?\d?|[1-9]\d?)){3}"
)

IPV6_REGEX = re.compile(r"(?:[a-f0-9]{1,4}:){7}[a-f0-9]{1,4}")


class BaseFormat:
    """Base protocol for converting textual input into native Python values.

    Concrete subclasses implement both native-type detection and string parsing.
    """

    error_messages: dict[str, str] = {}

    def validation_error(self, code: str) -> ValidationError:
        text = self.error_messages[code].format(**self.__dict__)
        return ValidationError(text=text, code=code)

    def is_native_type(self, value: typing.Any) -> bool:
        raise NotImplementedError()  # pragma: no cover

    def check(self, value: typing.Any) -> typing.Any | ValidationError:
        raise NotImplementedError()  # pragma: no cover


class DateFormat(BaseFormat):
    """Parse ISO-like `YYYY-MM-DD` strings into `datetime.date`.

    Invalid dates produce a `ValidationError` with a Saffier-specific code.
    """

    error_messages = {
        "format": "Must be a valid date format.",
        "invalid": "Must be a real date.",
    }

    def is_native_type(self, value: typing.Any) -> bool:
        return isinstance(value, datetime.date)

    def check(self, value: typing.Any) -> datetime.date:
        match = DATE_REGEX.match(value)
        if not match:
            raise self.validation_error("format")

        kwargs = {k: int(v) for k, v in match.groupdict().items()}
        try:
            return datetime.date(**kwargs)
        except ValueError:
            raise self.validation_error("invalid")  # noqa


class TimeFormat(BaseFormat):
    """Parse ISO-like time strings into `datetime.time`.

    Fractional seconds are padded to microsecond precision when present.
    """

    error_messages = {
        "format": "Must be a valid time format.",
        "invalid": "Must be a real time.",
    }

    def is_native_type(self, value: typing.Any) -> bool:
        return isinstance(value, datetime.time)

    def check(self, value: typing.Any) -> datetime.time:
        match = TIME_REGEX.match(value)
        if not match:
            raise self.validation_error("format")

        groups = match.groupdict()
        if groups["microsecond"]:
            groups["microsecond"] = groups["microsecond"].ljust(6, "0")

        kwargs = {k: int(v) for k, v in groups.items() if v is not None}
        try:
            return datetime.time(tzinfo=None, **kwargs)
        except ValueError:
            raise self.validation_error("invalid")  # noqa


class DateTimeFormat(BaseFormat):
    """Parse ISO-like datetime strings with optional timezone offsets.

    The parser supports both `T` and space separators plus `Z` or offset
    suffixes.
    """

    error_messages = {
        "format": "Must be a valid datetime format.",
        "invalid": "Must be a real datetime.",
    }

    def is_native_type(self, value: typing.Any) -> bool:
        return isinstance(value, datetime.datetime)

    def check(self, value: typing.Any) -> datetime.datetime:
        match = DATETIME_REGEX.match(value)
        if not match:
            raise self.validation_error("format")

        groups = match.groupdict()
        if groups["microsecond"] is not None:
            groups["microsecond"] = groups["microsecond"].ljust(6, "0")

        tzinfo_str = groups.pop("tzinfo")
        if tzinfo_str == "Z":
            tzinfo = datetime.timezone.utc
        elif tzinfo_str is not None:
            offset_mins = int(tzinfo_str[-2:]) if len(tzinfo_str) > 3 else 0
            offset_hours = int(tzinfo_str[1:3])
            delta = datetime.timedelta(hours=offset_hours, minutes=offset_mins)
            if tzinfo_str[0] == "-":
                delta = -delta
            tzinfo = datetime.timezone(delta)
        else:
            tzinfo = None

        kwargs = {k: int(v) for k, v in groups.items() if v is not None}
        try:
            return datetime.datetime(**kwargs, tzinfo=tzinfo)
        except ValueError:
            raise self.validation_error("invalid")  # noqa


class UUIDFormat(BaseFormat):
    """Validate UUID strings before converting them to `uuid.UUID`.

    Native `uuid.UUID` instances are passed through unchanged by callers.
    """

    error_messages = {"format": "Must be a valid UUID format."}

    def is_native_type(self, value: typing.Any) -> bool:
        return isinstance(value, uuid.UUID)

    def check(self, value: typing.Any) -> uuid.UUID:
        match = UUID_REGEX.match(value)
        if not match:
            raise self.validation_error("format")

        return uuid.UUID(value)


class EmailFormat(BaseFormat):
    """Validate e-mail addresses using Saffier's regex-based parser.

    The formatter returns the original string when validation succeeds.
    """

    error_messages = {"format": "Must be a valid email format."}

    def is_native_type(self, value: typing.Any) -> bool:
        return False

    def check(self, value: str) -> str:
        match = EMAIL_REGEX.match(value)
        if not match:
            raise self.validation_error("format")

        return value


class IPAddressFormat(BaseFormat):
    """Validate IPv4 and IPv6 strings and return `ipaddress` objects.

    Both regex prechecks and the stdlib parser are used for validation.
    """

    error_messages = {
        "format": "Must be a valid IP format.",
        "invalid": "Must be a real IP.",
    }

    def is_native_type(self, value: typing.Any) -> bool:
        return isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address))

    def check(self, value: typing.Any) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
        match_ipv4 = IPV4_REGEX.match(value)
        match_ipv6 = IPV6_REGEX.match(value)
        if not match_ipv4 and not match_ipv6:
            raise self.validation_error("format")

        try:
            return ipaddress.ip_address(value)
        except ValueError:
            raise self.validation_error("invalid")  # noqa


class URLFormat(BaseFormat):
    """Validate absolute URLs with a scheme and network location.

    Relative URLs are rejected because Saffier URL fields require fully
    qualified addresses.
    """

    error_messages = {"invalid": "Must be a real URL."}

    def is_native_type(self, value: typing.Any) -> bool:
        return False

    def check(self, value: typing.Any) -> str:
        url = urlparse(value)
        if not all([url.scheme, url.netloc]):
            raise self.validation_error("invalid")

        return str(value)

"""Custom Click parameter types for tasktree argument validation."""

import re
from ipaddress import IPv4Address, IPv6Address, ip_address
from pathlib import Path

import click


class IPv4Type(click.ParamType):
    """IPv4 address parameter type."""

    name = "ipv4"

    def convert(self, value, param, ctx):
        try:
            IPv4Address(value)
            return value
        except ValueError:
            self.fail(f"{value} is not a valid IPv4 address", param, ctx)


class IPv6Type(click.ParamType):
    """IPv6 address parameter type."""

    name = "ipv6"

    def convert(self, value, param, ctx):
        try:
            IPv6Address(value)
            return value
        except ValueError:
            self.fail(f"{value} is not a valid IPv6 address", param, ctx)


class IPType(click.ParamType):
    """IP address parameter type (IPv4 or IPv6)."""

    name = "ip"

    def convert(self, value, param, ctx):
        try:
            ip_address(value)
            return value
        except ValueError:
            self.fail(f"{value} is not a valid IP address", param, ctx)


class HostnameType(click.ParamType):
    """Hostname parameter type."""

    name = "hostname"

    # RFC 1123 hostname validation (simplified)
    HOSTNAME_PATTERN = re.compile(
        r"^(?=.{1,253}$)(?!-)[a-zA-Z0-9-]{1,63}(?<!-)(\.(?!-)[a-zA-Z0-9-]{1,63}(?<!-))*$"
    )

    def convert(self, value, param, ctx):
        if not self.HOSTNAME_PATTERN.match(value):
            self.fail(f"{value} is not a valid hostname", param, ctx)
        return value


class EmailType(click.ParamType):
    """Email address parameter type."""

    name = "email"

    # Basic email validation pattern
    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def convert(self, value, param, ctx):
        if not self.EMAIL_PATTERN.match(value):
            self.fail(f"{value} is not a valid email address", param, ctx)
        return value


class URLType(click.ParamType):
    """URL parameter type."""

    name = "url"

    # Basic URL validation pattern
    URL_PATTERN = re.compile(
        r"^https?://"  # http:// or https://
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"  # domain...
        r"localhost|"  # localhost...
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # ...or ip
        r"(?::\d+)?"  # optional port
        r"(?:/?|[/?]\S+)$", re.IGNORECASE  # path
    )

    def convert(self, value, param, ctx):
        if not self.URL_PATTERN.match(value):
            self.fail(f"{value} is not a valid URL", param, ctx)
        return value


class PathType(click.ParamType):
    """Path parameter type that returns a Path object."""

    name = "path"

    def convert(self, value, param, ctx):
        return Path(value)


# Registry of custom types
CUSTOM_TYPES = {
    "ipv4": IPv4Type(),
    "ipv6": IPv6Type(),
    "ip": IPType(),
    "hostname": HostnameType(),
    "email": EmailType(),
    "url": URLType(),
    "path": PathType(),
}


def get_param_type(type_name: str) -> click.ParamType:
    """Get a Click parameter type by name."""
    if type_name in CUSTOM_TYPES:
        return CUSTOM_TYPES[type_name]

    # Fall back to built-in Click types
    if type_name == "str":
        return click.STRING
    elif type_name == "int":
        return click.INT
    elif type_name == "float":
        return click.FLOAT
    elif type_name == "bool":
        return click.BOOL
    elif type_name == "datetime":
        return click.DateTime()

    # Default to string if unknown
    return click.STRING
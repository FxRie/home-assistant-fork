"""Helper for Netatmo integration."""

from __future__ import annotations

from collections.abc import Iterable, MutableSequence
from dataclasses import dataclass
from enum import Enum, IntEnum, StrEnum
from typing import Any, Self
from uuid import UUID, uuid4


@dataclass
class NetatmoArea:
    """Class for keeping track of an area."""

    area_name: str
    lat_ne: float
    lon_ne: float
    lat_sw: float
    lon_sw: float
    mode: str
    show_on_map: bool
    uuid: UUID = uuid4()


def try_pop[TColItem](
    seq: MutableSequence[TColItem],
    index: int = -1,
    default: TColItem | None = None,
) -> TColItem | None:
    """Extension to try and pop index or last item with no exception."""
    try:
        return seq.pop(index=index)
    except (IndexError, TypeError):
        return default


def iter_first_or_default[TCollectionType](
    iterable: Iterable[TCollectionType], default: TCollectionType | None = None
) -> TCollectionType | None:
    """Returns the first or default if defined of a Iterable object or None."""
    iterator = iter(iterable)
    return next(iterator, default)


def try_parse_enum[TEnum: Enum](
    enum_class: type[TEnum],
    value: int | str | Enum | None,
    fallback: TEnum | None = None,
) -> TEnum | None:
    """Tries to parse a string or Enum into an Enum member.    Matches by name or value (case-insensitive if strings).    Returns fallback (or None) if parsing fails."""
    if value is None:
        return fallback

    if isinstance(value, enum_class):
        return value

    if not isinstance(value, str):
        return fallback

    # Try name match (case-insensitive)
    for member in enum_class:
        if member.name.lower() == value.lower():
            return member

    # Try value match (case-insensitive if str)
    for member in enum_class:
        if isinstance(member.value, str) and member.value.lower() == value.lower():
            return member
        if member.value == value:
            return member

    return fallback


def try_parse[TTargetType](
    target_type: type[TTargetType], value: Any, default: TTargetType | None = None
) -> TTargetType | None:
    """This method tries to parse any given to a type and results in Unknown or a default if fails."""
    if not isinstance(value, target_type):
        return default
    return value


class BaseStrEnum(StrEnum):
    """This is an strEnum extension to map for pattern matching."""

    @classmethod
    def try_get_enum_by_val(
        cls, value: str | None, default: Self | None = None
    ) -> Self | None:
        """Attempt to convert a value to an enum member. Returns `default` if the value is not valid."""
        if not isinstance(value, str):
            return default
        try:
            return cls(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def match_value(cls, value: Any | None, default: Self | None = None) -> Self:
        """Helper for pattern matching. Returns the enum member or raises if invalid."""
        if not isinstance(value, str):
            return default if default is not None else next(iter(cls))
        enum_member = cls.try_get_enum_by_val(value, default)
        if enum_member is None:
            # fallback to default or first enum member
            return default if default is not None else next(iter(cls))
        return enum_member


class BaseIntEnum(IntEnum):
    """This is an intEnum extension to map for pattern matching."""

    @classmethod
    def try_get_enum_by_val(
        cls, value: int | None, default: Self | None = None
    ) -> Self | None:
        """Attempt to convert a value to an enum member. Returns `default` if the value is not valid."""
        if not isinstance(value, int):
            return default
        try:
            return cls(value)
        except (ValueError, TypeError):
            return default

    @classmethod
    def match_value(cls, value: Any | None, default: Self | None = None) -> Self:
        """Helper for pattern matching. Returns the enum member or raises if invalid."""
        if not isinstance(value, int):
            return default if default is not None else next(iter(cls))
        enum_member = cls.try_get_enum_by_val(value, default)
        if enum_member is None:
            # fallback to default or first enum member
            return default if default is not None else next(iter(cls))
        return enum_member

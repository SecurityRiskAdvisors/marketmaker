# note: IDEs such as PyCharm will mark these typing imports as unused even if they are used indirectly
#   for type hinting
from typing import List, Optional, Any, Union, TypeVar, Set, Tuple, Callable
from enum import Enum, auto
from pathlib import Path

StrOrPath = Union[str, Path]
OptionalStrList = Optional[List[Union[str, None]]]
StrSetOrList = Union[Set[str], List[str]]
EnumT = TypeVar("EnumT", bound=Enum)


class CaseInsensitiveEnum(Enum):
    """
    enum that allows for case-insensitive member lookup by name
    CaseInsensitiveEnum("key") -> CaseInsensitiveEnum.Key
    """

    @classmethod
    def _missing_(cls, value):
        # see: https://docs.python.org/3/library/enum.html#enum.Enum._missing_
        #   note that the lookup here is by name rather than by value
        for member in cls:
            if member.name.lower() == value.lower():
                return member
        raise KeyError(f"{value} is not a valid enum member")


CaseInsensitiveEnumT = TypeVar("CaseInsensitiveEnumT", bound=CaseInsensitiveEnum)


class Format(CaseInsensitiveEnum):
    Blueprint = auto()
    Variant = auto()
    Manifest = auto()


class OutputPrefixes:
    """common prefixes for stdout info; for use in CLI application"""

    Neutral = "[-]"
    Good = "[+]"
    Bad = "[x]"

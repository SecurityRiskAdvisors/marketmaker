from dataclasses import dataclass
import shlex
from abc import abstractmethod
from sqlalchemy import cast
from sqlalchemy.orm.query import Query
from sqlalchemy import exc
import warnings

from .type import Enum, auto, Union, TypeVar, Optional, Any, List, CaseInsensitiveEnum
from .sql import session, Variant, Blueprint, StrListType
from .config import global_settings
from .log import LoggedException

if not global_settings.experimental_features:
    raise LoggedException("Selectors cannot be used without enabling experimental features")


class SelectorKeyEnum(Enum):
    """
    same as .type.CaseInsensitiveEnum but strips underscores from value ("key_one" -> "keyone")
    """

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.name.lower() == value.lower().replace("_", ""):
                return member
        raise KeyError(f"{value} is not a valid enum member")

    @property
    @abstractmethod
    def is_special(self) -> bool:
        return False


class VariantSelectorKey(SelectorKeyEnum):
    Id = auto()
    Tid = auto()
    Tactic = auto()
    Name = auto()

    # special key types
    #   RequiresLadmin -> requires Local Administrator -> checks for "local_admin" prereq
    RequiresLadmin = auto()

    @property
    def column(self):
        if not self.is_special:
            return getattr(Variant, self.name.lower())
        else:
            return

    @property
    def is_special(self) -> bool:
        return self in [self.RequiresLadmin]


class BlueprintSelectorKey(SelectorKeyEnum):
    Id = auto()
    Name = auto()
    Prefix = auto()

    @property
    def column(self):
        return getattr(Blueprint, self.name.lower())

    @property
    def is_special(self) -> bool:
        return False


SelectorKeyT = TypeVar("SelectorKey", bound=SelectorKeyEnum)


class SelectorType(CaseInsensitiveEnum):
    Variant = auto()
    Blueprint = auto()

    @property
    def table(self):
        if self == SelectorType.Blueprint:
            return Blueprint
        elif self == SelectorType.Variant:
            return Variant
        else:
            raise NotImplementedError

    @property
    def key_type(self):
        if self == SelectorType.Blueprint:
            return BlueprintSelectorKey
        elif self == SelectorType.Variant:
            return VariantSelectorKey
        else:
            raise NotImplementedError


class SelectorProps:
    PREFIX = "selector"
    CTR_START = "("
    CTR_END = ")"


@dataclass
class SelectorFilter:
    key: SelectorKeyT
    value: Optional[Any]
    approximate: bool = False

    def _special_key_to_filter(self, query: Query) -> Query:
        """implements the logic for handling special key types"""
        # TODO: not sure if this is best implemented on the filter or the key
        #       currently doing it on filter in the event the value needs to be accessed
        if self.key.is_special:
            if self.key == VariantSelectorKey.RequiresLadmin:
                # TODO: i dont think this handles lists with multiple items
                return query.filter(Variant.prerequisites.ilike(cast(["local_admin"], StrListType)))
        return query

    def apply_to_query(self, query: Query) -> Query:
        """apply the filter to an SA query as an SA filter"""
        col = self.key.column
        if not self.key.is_special:
            if not self.approximate:
                query = query.filter(col == self.value)
            else:
                query = query.filter(col.ilike(f"%{self.value}%"))
        else:
            query = self._special_key_to_filter(query=query)
        return query


@dataclass
class Selector:
    type: SelectorType
    filters: List[SelectorFilter]

    @classmethod
    def from_str(cls, v: str):
        left_side = f"{SelectorProps.PREFIX}{SelectorProps.CTR_START}"
        right_side = SelectorProps.CTR_END
        if v.startswith(left_side) and v.endswith(right_side):
            v = v.replace(left_side, "").replace(right_side, "")
            selector_type_str = v.split(" ")[0]
            try:
                selector_type = SelectorType(selector_type_str)
            except KeyError as e:
                raise e

            # Lark feels a bit heavy for what this currently supports
            # but will revisit if this needs expanding
            selectors = v.replace(f"{selector_type_str} ", "")
            filters = []
            for token in shlex.split(selectors):
                approximate_cmp = False
                if "==" in token:
                    selector_key, selector_value = token.split("==")
                elif "~=" in token:
                    selector_key, selector_value = token.split("~=")
                    approximate_cmp = True
                else:
                    selector_key, selector_value = token, None
                filters.append(
                    SelectorFilter(
                        key=selector_type.key_type(selector_key), value=selector_value, approximate=approximate_cmp
                    )
                )
            return cls(type=selector_type, filters=filters)

        raise ValueError(f"Value {v} is not a valid selector")

    def get_matches(self):
        table = self.type.table
        query = session.query(table)
        for f in self.filters:
            query = f.apply_to_query(query=query)

        # suppress SA warning about caching on the custom list type
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=exc.SAWarning)
            results = query.all()

        return results

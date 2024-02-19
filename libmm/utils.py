import os
from ruamel.yaml import YAML
from pathlib import Path
import random
import string
import re
import json
from uuid import UUID
import io

from .type import List, StrOrPath, Optional, Any, Union

JSON_DUMP_ARGS = {"indent": 4, "sort_keys": True}


_y = YAML(typ="rt", pure=True)
_y.width = float("inf")  # disable line wrapping based on width
# custom representer to have empty lists display as None
original_list_repr = _y.representer.yaml_representers[list]


def new_list_repr(self, data):
    """list representer for ruamel for 0-length lists to treat values as empty strings"""
    if len(data) == 0:
        return self.represent_scalar("tag:yaml.org,2002:null", "")
    return original_list_repr(self, data)


_y.representer.yaml_representers[list] = new_list_repr


def get_yaml_o() -> YAML:
    """returns a ruamel YAML object configured for round-trip loading"""
    return _y


class COLORS:
    """shared colors"""

    BLUE = "#0377fc"
    RED = "#d41919"
    PURPLE = "#7a34eb"


# https://stackoverflow.com/a/50173148
def deep_get(d: dict, keys: List) -> Optional[Any]:
    """safely get a nested value from a dict if it exists"""
    if not keys or d is None:
        return d
    return deep_get(d.get(keys[0]), keys[1:])


def deep_pop(d: dict, keys: List):
    """safely pop a nested value from a dict if it exists"""
    if len(keys) == 1:
        try:
            del d[keys[0]]
        except KeyError:
            pass
    elif len(keys) > 1:
        if keys[0] in d and isinstance(d[keys[0]], dict):
            deep_pop(d[keys[0]], keys[1:])


def gen_random_string(length: int = 8) -> str:
    """return a random n-length string that uses only digits and lowercase letters"""
    return "".join(random.choice(string.ascii_lowercase + string.digits) for _ in range(length))


def resolve_str_or_path(path: StrOrPath) -> Path:
    """given a string or a pathlib Path, return the resolved Path"""
    return path.resolve() if type(path) == Path else Path(path).resolve()


def load_yaml_from_file(yaml_file: StrOrPath) -> dict:
    """return the deserialized yaml data from the provided file path"""
    return get_yaml_o().load(resolve_str_or_path(yaml_file))


def dump_yaml_to_file(yaml_: dict, yaml_file: StrOrPath):
    """serialize the provided dict to the file path"""
    get_yaml_o().dump(yaml_, resolve_str_or_path(yaml_file))


def dump_yaml_to_str(yaml_: dict) -> str:
    """serialize the provided dict to the file path"""
    strbuf = io.StringIO()
    get_yaml_o().dump(yaml_, strbuf)
    result = strbuf.getvalue()
    strbuf.close()
    return result


def load_json_from_file(json_file: StrOrPath) -> dict:
    """return the deserialized json data from the provided file path"""
    return json.loads(resolve_str_or_path(json_file).read_bytes())


def dump_json_to_file(json_: dict, json_file: StrOrPath):
    """serualize the provided dict to the file path"""
    resolve_str_or_path(json_file).write_text(json.dumps(json_, **JSON_DUMP_ARGS))


def strip_strlist(strlist: List[Union[str, None]]) -> List[str]:
    """given a list of strings, return a list will all empty/blank items removed"""
    return [item for item in strlist if item is not None and item != ""]


def condense_spaces(s: str) -> str:
    """replace all instance of >=3 newlines (\n) with a single double newline (\n\n)"""
    return re.sub(r"\n{3,}", "\n\n", s, flags=re.MULTILINE)


def compare_set_overlap(set1: set, set2: set) -> float:
    """given two sets, return the shared overlap as a decimal"""
    shared = set1.intersection(set2)
    total = set1.union(set2)
    return len(shared) / len(total)


def is_uuid(v) -> bool:
    """checks if the provided value is a valid UUID"""
    try:
        UUID(v)
        return True
    # exception could be one of many so just catch them all
    #   e.g. UUID("abc") is a ValueError but UUID(123) is an AttributeError
    except Exception:
        return False


def path_is_writable(path: StrOrPath) -> bool:
    """checks if the provided path is writable"""
    return os.access(resolve_str_or_path(path), os.W_OK)

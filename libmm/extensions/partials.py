from enum import Enum, auto
from sqlalchemy import event

from libmm.sql import Variant
from libmm.extension import AbstractUserHook, UserHookSetting, EventTypes
from libmm.utils import deep_get, load_yaml_from_file, strip_strlist
from libmm.log import logger
from libmm.type import List


"""
This extension hooks the SQLAlchemy events for modifying a Variant
to add resolution for partials in block and detect fields.
Partials are canned statements stored in a mapping file and prefixed with a static string ("partial::").
"""


class PartialsSettings(Enum):
    File = auto()
    Prefix = auto()


class NoCliHookSetting(UserHookSetting):
    @property
    def cli_arg(self):
        return None


class PartialsHook(AbstractUserHook):
    def __init__(self):
        self.enabled = True
        self.prefix = "partial::"
        self.__settings = {
            PartialsSettings.File: NoCliHookSetting(name="file", parent=self),
        }

        self._partials = {}

    @property
    def name(self):
        return "partials"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: PartialsSettings):
        return self.__settings.get(setting).value

    def set_value(self, setting: PartialsSettings, value):
        return self.__settings.get(setting).value_callback(value)

    def hook(self, event_type, context):
        if event_type == EventTypes.DbReady:
            self.do_start()

    def do_start(self):
        partials_file = self.get_value(PartialsSettings.File)
        if partials_file in ["", None]:
            self.enabled = False
            logger.warn(f'Extension "{self.name}" disabled due to missing values')
        else:
            self._partials = load_yaml_from_file(partials_file)

    def resolve_list_of_partials(self, inputs: List[str]) -> List[str]:
        """
        given a list of strings, resolve each list item:
        - if it is a partial and it can be resolved, or it is not a partial -> add that to the list
        - if it is a partial and cannot be resolved -> ignore it
        """
        results = []
        for item in inputs:
            if len(split := item.split(self.prefix)) > 1:
                partial = split[-1]
                if "." in partial:
                    partial_keys = partial.split(".")
                else:
                    partial_keys = [partial]
                if (resolved := deep_get(self._partials, partial_keys)) is not None:
                    results.append(resolved)
                else:
                    logger.error(f'Could not resolve partial "{item}"')
            else:
                results.append(item)
        return results


hook = PartialsHook()


def resolve_event_value(target: Variant):
    if target.detect and len(strip_strlist(target.detect)) > 0:
        target.detect = hook.resolve_list_of_partials(inputs=target.detect)
    if target.block and len(strip_strlist(target.block)) > 0:
        target.block = hook.resolve_list_of_partials(inputs=target.block)


@event.listens_for(Variant, "before_insert")
def recv_variant_before_insert(mapper, connection, target):
    resolve_event_value(target)


@event.listens_for(Variant, "before_update")
def recv_variant_before_update(mapper, connection, target):
    resolve_event_value(target)

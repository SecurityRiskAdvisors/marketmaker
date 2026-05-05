from enum import Enum, auto
from importlib.resources import path as resource_path
from functools import lru_cache

from libmm.extension import AbstractUserHook, EventTypes, TestCaseRenderContext, NoCliHookSetting
from libmm.log import logger
from libmm.config import global_settings
from libmm.mitre import get_mitre_tactic_id_map, get_valid_tactic_ids_for_tid
from libmm.utils import load_json_from_file

"""
This extension will modify exported Variants to migrate revoked ATT&CK Technique IDs to their closest supported equivalent.
It operates using two modes. In pre-v19 mode, it uses a manual mapping of migration for revoked techniques ("PRE19_MIGRATION_MAP"). If not in pre-v19 mode, the user can enable the v19 crosswalk to migrate using the MITRE provided crosswalk mapping from https://attack.mitre.org/docs/subtechniques/de-split-crosswalk.json (bundled in this extension's data; "v19-crosswalk.json"). 

Since the Variant schema does not include a MITRE ATT&CK version, we cannot reliably apply crosswalks automatically. Future version of Market Maker may add this in Variant metadata.    
"""


PRE19_MIGRATION_MAP = {
    # removed in v17: https://attack.mitre.org/resources/updates/updates-april-2025/
    "T1574.002": "T1574.001"
}


@lru_cache(maxsize=None)
def get_v19_crosswalk():
    with resource_path("libmm", "extensions") as p:
        p = p / "attackmigrate" / "v19-crosswalk.json"
        crosswalk = load_json_from_file(p)
    return crosswalk


class AttackMigrateSettings(Enum):
    CrosswalkV19 = auto()


class AttackMigrateHook(AbstractUserHook):
    def __init__(self):
        self.enabled = True
        self.__settings = {
            AttackMigrateSettings.CrosswalkV19: NoCliHookSetting(name="v19crosswalk", parent=self),
        }
        self._crosswalk = get_v19_crosswalk()
        self._tactics = get_mitre_tactic_id_map(use_shortnames=True)

    @property
    def name(self):
        return "attackmigrate"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: AttackMigrateSettings):
        return self.__settings.get(setting).value

    def set_value(self, setting: AttackMigrateSettings, value):
        return self.__settings.get(setting).value_callback(value)

    def hook(self, event_type, context):
        if self.enabled:
            if event_type == EventTypes.TestCaseRender:
                self.do_render(context)

    def _tactic_id_to_shortname(self, tactic_id):
        for shortname, id_ in self._tactics.items():
            if id_ == tactic_id:
                return shortname

    def do_render(self, context: TestCaseRenderContext):
        variant = context.variant
        technique_id = variant["metadata"]["tid"]
        tactic_id = variant["metadata"]["tactic"]

        if global_settings.pre_attack_19:
            if technique_id in PRE19_MIGRATION_MAP:
                new_technique_id = PRE19_MIGRATION_MAP.get(technique_id)
                variant["metadata"]["tid"] = new_technique_id
                logger.warning(
                    f'Revoked Technique ID detected! Changing "{technique_id}" to "{new_technique_id}". Consider updating source Variant.'
                )

        else:
            apply_v19_crosswalk = bool(self.get_value(AttackMigrateSettings.CrosswalkV19))
            if apply_v19_crosswalk and technique_id in (
                existing_techniques := self._crosswalk.get("existing-techniques", {})
            ):
                if technique_crosswalk := existing_techniques.get(technique_id, None):
                    new_technique_id = technique_crosswalk.get("attack-v19-attack-id")
                    variant["metadata"]["tid"] = new_technique_id

                    logger.info(f'Migrating TID from "{technique_id}" to "{new_technique_id}".')

                    # note: be mindful of calling mitre-related functions when dealing with v19 mode
                    # for example, if the source library data is pre-v19, then you do not want to
                    # call mitre functions when market maker is not in pre-v19 mode as you will get tactic mismatches
                    #
                    # in this case, we assume the source data is pre-v19 since we are applying the crosswalk.
                    # since market maker is not in pre-v19 mode, tactic names will be the v19 version.
                    # this only matters for defense evasion so simply override it before use
                    # (att&ck < v19 TA0005 = defense evasion, >= v19 = stealth)
                    tactic_shortname = self._tactic_id_to_shortname(tactic_id)
                    if tactic_shortname == "stealth":
                        tactic_shortname = "defense-evasion"

                    # only migrate the tactic when its not in the new tactic list
                    # otherwise keep as-is
                    if tactic_shortname not in (new_tactic_list := technique_crosswalk.get("attack-v19-tactics")):
                        new_tactic = new_tactic_list[0]

                        if len(new_tactic_list) > 1:
                            # if the original tactic was defense evasion, prefer one of its newer replacements
                            if tactic_shortname == "defense-evasion":
                                if "defense-impairment" in new_tactic_list:
                                    new_tactic = "defense-impairment"
                                elif "stealth" in new_tactic_list:
                                    new_tactic = "stealth"

                            # log a warning when there are >1 new tactics as this might
                            # be an undesirable change
                            logger.warning(
                                f'Migrating Tactic to "{new_tactic}" for "{new_technique_id}" (original: "{technique_id}"). Tactic selected from multiple possible options.'
                            )

                        else:
                            logger.info(
                                f'Migrating Tactic to "{new_tactic}" for "{new_technique_id}" (original: "{technique_id}").'
                            )

                        new_tactic_id = self._tactics.get(new_tactic)
                        variant["metadata"]["tactic"] = new_technique_id


hook = AttackMigrateHook()

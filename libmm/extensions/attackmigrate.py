from libmm.extension import AbstractUserHook, EventTypes, TestCaseRenderContext
from libmm.log import logger

"""
This extension will modify exported Variants to migrate revoked ATT&CK Technique IDs to their closest supported equivalent.
This uses a manual mapping of old to new Technique IDs. However, ATT&CK CTI data does include revocation information.
For example, https://center-for-threat-informed-defense.github.io/attack-sync/v16.1-v17.0/enterprise-attack/techniques/
    notes that "T1574.002" is replaced by "T1574.001".
Future updates may switch to the CTI mappings.
"""


MIGRATION_MAP = {
    # removed in v17: https://attack.mitre.org/resources/updates/updates-april-2025/
    "T1574.002": "T1574.001"
}


class AttackMigrateHook(AbstractUserHook):
    def __init__(self):
        self.enabled = True

    @property
    def name(self):
        return "attackmigrate"

    @property
    def settings(self):
        return []

    def hook(self, event_type, context):
        if self.enabled:
            if event_type == EventTypes.TestCaseRender:
                self.do_render(context)

    @staticmethod
    def do_render(context: TestCaseRenderContext):
        variant = context.variant
        technique_id = variant["metadata"]["tid"]
        if technique_id in MIGRATION_MAP:
            new_technique_id = MIGRATION_MAP.get(technique_id)
            variant["metadata"]["tid"] = new_technique_id
            logger.warn(
                f'Revoked Technique ID detected! Changing "{technique_id}" to "{new_technique_id}". Consider updating source Variant.'
            )


hook = AttackMigrateHook()

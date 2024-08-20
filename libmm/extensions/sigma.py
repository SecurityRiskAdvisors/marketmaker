import pathlib
from enum import Enum, auto
import click
import urllib.request
import json
from sigma.collection import SigmaCollection
from uuid import UUID
import zipfile
import tempfile
import shutil
import io

from libmm.sql import (
    Blueprint,
    SQLModel,
    session,
    Field,
    DictType,
    Column,
    Variant,
    create_all_tables,
    LinkedData,
    LinkedDataTarget,
    LinkedDataFormat,
)
from libmm.extension import AbstractUserHook, UserHookSetting, EventTypes, UserHookSettingT, NoCliHookSetting
from libmm.utils import resolve_str_or_path, condense_spaces, load_yaml_from_file, dump_yaml_to_str
from libmm.type import OutputPrefixes, List
from libmm.log import logger, LoggedException

"""
This extension generates a Markdown document of Sigma rules for a Blueprint based on a mapping
of Variants to Sigma rule IDs.
"""

MARKDOWN_NEWLINE = "\n\n"
ASSET_NAME = "sigma_core++"
ZIP_URL = f"https://github.com/SigmaHQ/sigma/releases/latest/download/{ASSET_NAME}.zip"

# mapping format:
# {"f20b84e2-e31a-4423-8396-f701d28926d6": ["63665c93-dd47-45b5-80fa-c5502c9e12ed"]}


class SigmaRule(SQLModel, table=True):
    id: int = Field(primary_key=True)
    rule_id: str
    variant_id: str = Field(foreign_key="variant.id")
    rule: dict = Field(sa_column=Column(DictType))

    @property
    def variant(self):
        return session.query(Variant).filter(Variant.id == self.variant_id).first()


class SigmaSettings(Enum):
    DetectionBundlePath = auto()
    Mapping = auto()
    RulesPaths = auto()


class SigmaHook(AbstractUserHook):
    def __init__(self):
        self.enabled = False
        self.__settings = {
            SigmaSettings.DetectionBundlePath: UserHookSetting(name="path", parent=self),
            SigmaSettings.Mapping: NoCliHookSetting(name="mapping", parent=self),
            SigmaSettings.RulesPaths: NoCliHookSetting(name="rules", parent=self),
        }
        self._rules = SigmaCollection([])
        self._document = ""
        self._mappings = dict()

        self._first_loaded = False
        self._link_populated = False

    @property
    def name(self):
        return "sigma"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: SigmaSettings):
        return self.__settings.get(setting).value

    def do_first_load(self):
        if not self._first_loaded:
            create_all_tables()
            self._mappings = load_yaml_from_file(self.get_value(SigmaSettings.Mapping))

            rule_paths = self.get_value(SigmaSettings.RulesPaths)
            if rule_paths == "latest":
                logger.info(f"Loading {ASSET_NAME} rules from GitHub")
                request = urllib.request.Request(ZIP_URL, method="GET")
                response = urllib.request.urlopen(request)
                if response.status != 200:
                    logger.error(f"Error downloading rules zip from Github: {response.reason} ({response.status})")
                    return
                zipdata = response.read()
                zipdata_io = io.BytesIO(zipdata)
                zipf = zipfile.ZipFile(zipdata_io)
                tmp_dir = tempfile.mkdtemp()
                zipf.extractall(tmp_dir)
                tmp_rules_path = f"{tmp_dir}/rules"
                self._rules = SigmaCollection.load_ruleset([tmp_rules_path])
                shutil.rmtree(tmp_dir)
            else:
                logger.info(f"Loading rules from local system")
                if ":" in rule_paths:
                    rule_paths = rule_paths.split(":")
                else:
                    rule_paths = [rule_paths]
                self._rules = SigmaCollection.load_ruleset(rule_paths)

            if len(self._mappings) == 0:
                logger.warn(f'Extension "{self.name}" disabled due to empty mapping')
                self.enabled = False
                return
            if len(self._rules) == 0:
                logger.warn(f'Extension "{self.name}" disabled due to no rules being loaded')
                self.enabled = False
                return

            for variant_id, rule_ids in self._mappings.items():
                # based on the provided mapping, only persist rules that are tied to a Variant.
                for rule_id in rule_ids:
                    # the ids_to_rules attr on the collection is a 1:1 mapping of rule UUIDs -> rules
                    # the key is the UUID as a UUID object, so string lookups wont work
                    rule_uuid = UUID(rule_id)
                    if rule_uuid in self._rules.ids_to_rules:
                        session.add(
                            SigmaRule(rule_id=rule_id, variant_id=variant_id, rule=self._rules[rule_uuid].to_dict())
                        )
                    else:
                        logger.warn(f"Sigma rule {rule_id} not found")
            session.commit()

            self._first_loaded = True

    def populate_linked_data(self):
        if not self._link_populated and self.enabled:
            for rule in session.query(SigmaRule).all():  # type: SigmaRule
                session.add(
                    LinkedData(
                        variant_id=rule.variant_id,
                        target_type=LinkedDataTarget.Variant,
                        data_format=LinkedDataFormat.Plaintext,
                        data=dump_yaml_to_str(rule.rule),
                        origin=self.name,
                        display_name="Sigma Rule",
                    )
                )
            session.commit()
            self._link_populated = True

    def hook(self, event_type, context):
        if event_type == EventTypes.CliStart:
            self.do_start(required_settings=self.settings)

        if event_type == EventTypes.LinkTableReady:
            self.do_start(
                required_settings=[self.__settings[SigmaSettings.Mapping], self.__settings[SigmaSettings.RulesPaths]]
            )
            self.populate_linked_data()

        if self.enabled:
            if event_type == EventTypes.CliExit:
                self.do_exit()

            if event_type == EventTypes.BlueprintLoaded:
                self.do_load(context)

    def do_start(self, required_settings: List[UserHookSettingT]):
        if not all([setting.value is not None for setting in required_settings]):
            self.enabled = False
            logger.warn(f'Extension "{self.name}" disabled due to missing values')
        else:
            self.enabled = True
            self.do_first_load()

    def do_exit(self):
        outpath = resolve_str_or_path(self.get_value(SigmaSettings.DetectionBundlePath))
        outpath.write_text(self._document)
        click.echo(f"{OutputPrefixes.Good} Writing detection bundle to {outpath.as_posix()}")

    def do_load(self, context):
        blueprint: Blueprint = context.blueprint
        document = ""

        for variant in blueprint.variants:
            if len(rules := session.query(SigmaRule).filter(SigmaRule.variant_id == variant.id).all()) > 0:
                document += f"# {variant.display_name}"
                document += MARKDOWN_NEWLINE
                document += f"ID: {variant.id}"
                document += MARKDOWN_NEWLINE

                for rule in rules:  # type: SigmaRule
                    document += "### Rule"
                    document += MARKDOWN_NEWLINE
                    document += "```yaml"
                    document += MARKDOWN_NEWLINE
                    document += dump_yaml_to_str(rule.rule)
                    document += MARKDOWN_NEWLINE
                    document += "```"
                    document += MARKDOWN_NEWLINE

        document = condense_spaces(document)
        self._document = document


hook = SigmaHook()

import re
from enum import Enum, auto
import click
from uuid import uuid4
from sqlalchemy import Column, String, Enum as SAEnum, event

from libmm.sql import (
    SQLModel,
    session,
    create_all_tables,
    Field,
    Variant,
    Blueprint,
    BlueprintCampaign,
    LinkedData,
    LinkedDataTarget,
    LinkedDataFormat,
)
from libmm.extension import (
    AbstractUserHook,
    UserHookSetting,
    EventTypes,
    BlueprintLoadedContext,
    NoCliHookSetting,
    UserHookSettingT,
)
from libmm.log import logger, LoggedException
from libmm.type import StrOrPath, OutputPrefixes, Optional, List, Set
from libmm.utils import (
    load_yaml_from_file,
    resolve_str_or_path,
    get_yaml_o,
    strip_strlist,
    condense_spaces,
)

"""
This extension generates a Markdown document with additional operator guidance based on a mapping
of Variant/Blueprint IDs to Guidance IDs. 
Guidance documents are structured Markdown documents (see "GuidanceDocument" class below)
"""


MARKDOWN_NEWLINE = "\n\n"


class GuidanceDocument(SQLModel, table=True):
    """
    markdown structure
        xx - front matter
        h1
          |- title
          |- description
          \\_ h2
              |- title & anchor
              |- description
              \\_ h3
                ...
          ...

    Example:
        ```
        ---
        x_guidance_id: 6906c906-52e6-4087-8c7b-8a4a70138c9d
        gsv: 1
        ---

        # Foo title

        Foo description

        ## [1] Bar subtitle

        Bar description

        ### Prerequisites

        Prerequisites description
        ```

        Where:
        - `x_guidance_id` is the guidance document UUID
        - `gsv` is always `1`
        - H1s/H2s are an arbitrary title
        - H2s start with [#] where # is the anchor identifier
        - H3s are one of the following (max one of each):
            - Prerequisites, Guidance, Cleanup, Notes, References

    Refer to extension documentation for additional details on document/mapping structure
    """

    id: int = Field(primary_key=True)
    uuid: str = Field(default_factory=lambda: str(uuid4()), sa_column=Column(String, unique=False))  # guid
    content: str  # entire guide contents
    gsv: int  # schema version
    anchor: int  # subguide version from original document

    @classmethod
    def load_all_from_paths(cls, paths: List[StrOrPath]):
        for path in paths:
            for f in resolve_str_or_path(path).rglob("*.md"):
                GuidanceDocument.from_file(f)

    @classmethod
    def from_file(cls, path: StrOrPath) -> List["GuidanceDocument"]:
        path = resolve_str_or_path(path)
        if path.exists():
            return cls.from_markdown(path.read_text())
        else:
            logger.warn(f'Guidance file "{path.as_posix()}" does not exist')

    @classmethod
    def from_markdown(cls, markdown: str) -> List["GuidanceDocument"]:
        guides = []

        md_split = markdown.split("---")
        front_matter = {}
        if len(md_split) > 1:
            markdown = "".join(md_split[2:])
            front_matter = get_yaml_o().load(md_split[1])
        try:
            guidance_id = front_matter["x_guidance_id"]
            gsv = front_matter["gsv"]
        except KeyError:
            # TODO: eventually have a schema check on guidance docs
            raise LoggedException("Guidance document missing required front matter")

        # process h2 sections
        #   index 0 is the preamble that belongs to the h1
        #   h1 -> h2 since it will be joined under a campaign-named h1
        #       will still be referred to as h1 for clarity
        sections_h2 = re.split(r"^##\s", markdown, flags=re.MULTILINE)
        title_and_descr_h1 = strip_strlist(sections_h2[0].strip().split("\n"))
        title_h1 = f"#{title_and_descr_h1[0]}"
        description_h1 = ""
        if len(title_and_descr_h1) > 1:  # sometimes there is no description
            description_h1 = title_and_descr_h1[-1]

        for subguide in sections_h2[1:]:
            sections_h3 = re.split(r"^###\s", subguide, flags=re.MULTILINE)
            title_and_descr_h3 = strip_strlist(sections_h3[0].strip().split("\n"))
            title_h3 = title_and_descr_h3[0]
            description_h3 = ""
            if len(title_and_descr_h3) > 1:
                description_h3 = title_and_descr_h3[-1]
            subguide_anchor = re.findall(r"^\[(.*)\]", title_h3)[0]
            subguide_title = title_h3.split(f"[{subguide_anchor}]")[-1].strip()
            sections_h3.pop(0)  # remove title/description from sections; remaining are the content

            merged_title = f"{title_h1} - {subguide_title}"
            merged_description = f"{description_h1.strip()}{MARKDOWN_NEWLINE}{description_h3.strip()}"

            subguide_text = ""
            subguide_text += merged_title
            subguide_text += MARKDOWN_NEWLINE
            subguide_text += merged_description
            subguide_text += MARKDOWN_NEWLINE
            subguide_text += "".join([f"### {h3}" for h3 in sections_h3])
            subguide_text = condense_spaces(subguide_text)

            guides.append(
                cls(
                    uuid=guidance_id,
                    anchor=int(subguide_anchor),
                    gsv=gsv,
                    content=subguide_text,
                )
            )

            for guide in guides:
                session.add(guide)
        session.commit()
        return guides


class GuidanceTarget(Enum):
    Variant = auto()
    Blueprint = auto()


class GuidanceMapping(SQLModel, table=True):
    id: int = Field(primary_key=True)
    # TODO: sqla rels
    guidance_id: str = Field(foreign_key="guidancedocument.uuid")
    guidance_anchor: int = Field(foreign_key="guidancedocument.anchor")
    target_id: str  # id of target
    target_type: Optional[GuidanceTarget] = Field(sa_column=Column(SAEnum(GuidanceTarget)), nullable=True)
    scope: str = Field(default="default")

    @classmethod
    def update_target_ids(cls):
        variants = session.query(Variant).all()
        variant_ids = [v.id for v in variants]
        blueprints = session.query(Blueprint).all()
        blueprint_ids = [b.id for b in blueprints]

        if mappings := session.query(GuidanceMapping).all():
            for mapping in mappings:  # type: GuidanceMapping
                if mapping.target_id in blueprint_ids:
                    mapping.target_type = GuidanceTarget.Blueprint
                elif mapping.target_id in variant_ids:
                    mapping.target_type = GuidanceTarget.Variant
                else:
                    logger.warn(f'Could not locate target with ID "{mapping.target_id}"')
                    continue
            session.commit()

    @classmethod
    def get_documents_for_object(cls, o, o_type: GuidanceTarget) -> Set[str]:
        documents = set()
        mappings = (
            session.query(GuidanceMapping)
            .filter(GuidanceMapping.target_id == o.id, GuidanceMapping.target_type == o_type)
            .all()
        )
        for mapping in mappings:  # type: GuidanceMapping
            if mapping.scope not in hook.scopes:
                continue

            doc: GuidanceDocument = (
                session.query(GuidanceDocument)
                .filter(
                    GuidanceDocument.uuid == mapping.guidance_id, GuidanceDocument.anchor == mapping.guidance_anchor
                )
                .first()
            )
            documents.add(doc.content)
        return documents

    @classmethod
    def populate_linked_data(cls):
        mappings: List[tuple] = session.query(GuidanceMapping).filter(GuidanceMapping.target_type.is_not(None)).all()
        for mapping in mappings:  # type: GuidanceMapping
            if mapping.scope not in hook.scopes:
                continue

            doc: GuidanceDocument = (
                session.query(GuidanceDocument)
                .filter(
                    GuidanceDocument.uuid == mapping.guidance_id, GuidanceDocument.anchor == mapping.guidance_anchor
                )
                .first()
            )

            if doc:
                session.add(
                    LinkedData(
                        blueprint_id=mapping.target_id if mapping.target_type == GuidanceTarget.Blueprint else None,
                        variant_id=mapping.target_id if mapping.target_type == GuidanceTarget.Variant else None,
                        target_type=LinkedDataTarget(mapping.target_type.name),
                        data_format=LinkedDataFormat.Markdown,
                        data=doc.content,
                        origin=hook.name,
                        display_name="Operator Guidance",
                    )
                )
                session.commit()

    @classmethod
    def from_mapping_yaml(cls, mapping: dict):
        """
        mapping format:

            <variant/bp uuid>:
            - id: <guidance uuid>
              anchor: <int>
        """
        for uuid, properties_list in mapping.items():  # type: str, dict
            for properties in properties_list:
                guidance_id = properties.get("id", None)
                guidance_entry = properties.get("entry", None)
                scope = properties.get("scope", "default")
                if not guidance_id or not guidance_entry:
                    logger.warn(f'Invalid mapping format for entry ID "{uuid}"')
                    continue
                session.add(cls(guidance_id=guidance_id, guidance_anchor=guidance_entry, target_id=uuid, scope=scope))
        session.commit()

    @classmethod
    def from_mapping_file(cls, path: StrOrPath):
        return cls.from_mapping_yaml(load_yaml_from_file(path))


class GuidanceSettings(Enum):
    Paths = auto()
    OpNotebook = auto()
    Mapping = auto()
    Scopes = auto()


class GuidanceHook(AbstractUserHook):
    def __init__(self):
        self.enabled = False
        self.__settings = {
            GuidanceSettings.Paths: NoCliHookSetting(name="paths", parent=self),
            GuidanceSettings.Mapping: NoCliHookSetting(name="mapping", parent=self),
            GuidanceSettings.OpNotebook: UserHookSetting(name="opnotebook", parent=self),
            GuidanceSettings.Scopes: UserHookSetting(name="scopes", parent=self),
        }

        self._mapping = None
        self._library = None
        self._notebook = ""

        self._first_loaded = False
        self._link_populated = False
        self._is_cli = False

    @property
    def name(self):
        return "guidance"

    @property
    def settings(self):
        return list(self.__settings.values())

    def get_value(self, setting: GuidanceSettings):
        return self.__settings.get(setting).value

    @property
    def scopes(self):
        if (value := self.get_value(GuidanceSettings.Scopes)) not in ["", None]:
            if "," in value:
                scopes = value.split(",")
                scopes = [scope.strip() for scope in scopes]
            else:
                scopes = [value.strip()]
        else:
            scopes = ["default"]

        return scopes

    def do_first_load(self):
        """
        Initial data loading of documents and mapping.
        This should only run once, regardless of the initial triggering mechanism
        """
        if not self._first_loaded:
            GuidanceDocument.load_all_from_paths(paths=self.get_value(GuidanceSettings.Paths).split(":"))
            GuidanceMapping.from_mapping_file(self.get_value(GuidanceSettings.Mapping))

            self._first_loaded = True

    def hook(self, event_type, context):
        if event_type == EventTypes.CliStart:
            self.do_start(
                required_settings=[
                    self.__settings[GuidanceSettings.Mapping],
                    self.__settings[GuidanceSettings.Paths],
                    self.__settings[GuidanceSettings.OpNotebook],
                ]
            )
            self._is_cli = True

        if event_type == EventTypes.DbReady:
            create_all_tables()
            self.do_start(
                required_settings=[self.__settings[GuidanceSettings.Mapping], self.__settings[GuidanceSettings.Paths]]
            )

        if self.enabled:
            if event_type == EventTypes.LinkTableReady:
                self.do_ld_load()

            if event_type == EventTypes.CliExit:
                self.do_exit()

            if event_type == EventTypes.BlueprintLoaded and self._is_cli:
                self.do_bp_load(context)

    def do_start(self, required_settings: List[UserHookSettingT]):
        if not all([setting.value not in [None, ""] for setting in required_settings]):
            self.enabled = False
            logger.warn(f'Extension "{self.name}" disabled due to missing values')
        else:
            self.enabled = True
            self.do_first_load()

    def do_exit(self):
        outpath = resolve_str_or_path(self.get_value(GuidanceSettings.OpNotebook))
        outpath.write_text(self._notebook)
        click.echo(f"{OutputPrefixes.Good} Writing operator notebook to {outpath.as_posix()}")

    def do_ld_load(self):
        GuidanceMapping.update_target_ids()
        if not self._link_populated:
            GuidanceMapping.populate_linked_data()
            self._link_populated = True

    def do_bp_load(self, context: BlueprintLoadedContext):
        # GuidanceMapping.update_target_ids()

        notebook = ""
        blueprint = context.blueprint

        blueprint_docs = GuidanceMapping.get_documents_for_object(blueprint, GuidanceTarget.Blueprint)

        if len(blueprint_docs) > 0:
            notebook += f"# General"
            notebook += MARKDOWN_NEWLINE
            for doc in blueprint_docs:
                notebook += doc
                notebook += MARKDOWN_NEWLINE

        for campaign in blueprint.child_campaigns:  # type: BlueprintCampaign
            campaign_docs = set()

            for variant in campaign.variants:  # type: Variant
                for doc in GuidanceMapping.get_documents_for_object(variant, GuidanceTarget.Variant):
                    # handle when one doc is mapped to multiple variants
                    # this is done a per-campaign basis
                    #   e.g. no dupes in a campaign, but dupes okay across campaigns
                    if doc not in campaign_docs:
                        campaign_docs.add(doc)

            if len(campaign_docs) > 0:
                notebook += f"# {campaign.name}"
                notebook += MARKDOWN_NEWLINE
                for doc in campaign_docs:
                    notebook += doc
                    notebook += MARKDOWN_NEWLINE

        self._notebook = condense_spaces(notebook)


hook = GuidanceHook()


@event.listens_for(Blueprint, "before_insert")
def recv_blueprint_before_insert(mapper, connection, target: Blueprint):
    session.query(GuidanceMapping).filter(GuidanceMapping.target_id == target.id).update(
        {GuidanceMapping.target_type: GuidanceTarget.Blueprint}
    )


@event.listens_for(Variant, "before_insert")
def recv_variant_before_insert(mapper, connection, target: Variant):
    session.query(GuidanceMapping).filter(GuidanceMapping.target_id == target.id).update(
        {GuidanceMapping.target_type: GuidanceTarget.Variant}
    )

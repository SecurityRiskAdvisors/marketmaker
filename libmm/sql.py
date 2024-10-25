from sqlmodel import create_engine, Field, String, Relationship
from sqlalchemy import Column, Enum as SAEnum
from sqlalchemy.orm import sessionmaker, scoped_session
import sqlalchemy.types as sa_types
from uuid import uuid4
from sqlmodel import SQLModel as OriginalSQLModel
from copy import copy
from pydantic import PrivateAttr
from collections import OrderedDict
from abc import abstractmethod
import json

from .config import global_settings
from .type import (
    OptionalStrList,
    Optional,
    List,
    StrOrPath,
    TypeVar,
    CaseInsensitiveEnumT,
    Any,
    CaseInsensitiveEnum,
    auto,
)
from .utils import load_yaml_from_file, resolve_str_or_path
from .log import logger, LoggedException
from .mitre import get_d3fend_off_artifacts_for_tid, get_d3fend_ctrm_for_artifact

# sqlmodel uses sqlalchemy v1.4 and pydantic 1.10


class SQLModel(OriginalSQLModel):
    # adds a post init to the sqlmodel class to mimic the dataclass behavior
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__post_init__()
        extensions_manager.emit_event(event=EventPairs.DbOjectInit, object=self)

    def __post_init__(self):
        pass

    @classmethod
    def count(cls):
        return session.query(cls).count()


class StrListType(sa_types.TypeDecorator):
    """
    SQLAlchemy type for list of strings.
    For serialization, converts list into delimited string based on global config delimiter.
    For deserialization, converts back using the same delimiter.
    Only modifies values when for non-null values.
    Note: You must use the same delimiter setting b/w different uses of the library otherwise
          the functionality will work as expected when deserializing.
    """

    impl = sa_types.String

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value == [None]:
                return ""
            return f"{global_settings.db_text_delimiter}".join(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return value.split(global_settings.db_text_delimiter)
        return value


class DictType(sa_types.TypeDecorator):
    """
    SQLAlchemy type for Python dict.
    For serialization, converts dict into string using default json.dumps().
    For deserialization, converts back using default json.loads().
    Only modifies values when for non-null values.
    """

    # TODO: some way to allow custom serializers for json.dumps()

    impl = sa_types.String

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return json.loads(value)
        return value


def str_list_field() -> Field:
    return Field(sa_column=Column(StrListType, nullable=True), nullable=True)


def uuid_field() -> Field:
    """Type-4 UUID primary key field"""
    return Field(default_factory=lambda: str(uuid4()), sa_column=Column(String, primary_key=True))


class VariantCampaignLink(SQLModel, table=True):
    campaign_id: Optional[str] = Field(default=None, foreign_key="blueprintcampaign.id", primary_key=True)
    variant_id: Optional[str] = Field(default=None, foreign_key="variant.id", primary_key=True)


class VariantGroupLink(SQLModel, table=True):
    group_id: Optional[str] = Field(default=None, foreign_key="blueprintgroup.id", primary_key=True)
    variant_id: Optional[str] = Field(default=None, foreign_key="variant.id", primary_key=True)


class Variant(SQLModel, table=True):
    id: str = uuid_field()
    mav: Optional[int]
    # md: dict = Field(sa_column=Column(PickleType))
    # TODO: field validators

    # misc
    filepath: str = Field(nullable=True)
    version: int
    name: str

    # core fields
    display_name: str
    description: str
    platforms: OptionalStrList = str_list_field()
    prerequisites: OptionalStrList = str_list_field()
    guidance: OptionalStrList = str_list_field()
    block: OptionalStrList = str_list_field()
    detect: OptionalStrList = str_list_field()
    controls: OptionalStrList = str_list_field()

    # metadata fields
    tactic: str
    tid: str
    tools: OptionalStrList = str_list_field()
    references: OptionalStrList = str_list_field()

    # many to many with campaigns
    campaigns: List["BlueprintCampaign"] = Relationship(back_populates="variants", link_model=VariantCampaignLink)
    # many to many with groups
    groups: List["BlueprintGroup"] = Relationship(back_populates="variants", link_model=VariantGroupLink)
    # one to many with overrides
    overrides: List["VariantOverride"] = Relationship(back_populates="variant")

    _x_metadata: dict = PrivateAttr(default_factory=dict)

    def __post_init__(self):
        from .checks import VariantChecks

        # perform runtime validation checks
        # TODO: once field validators are implemented, some of these checks can probably be
        #       converted into field validators

        """
        passed = VariantChecks.run_all(self)
        if not passed:
            raise LoggedException(f'Checks for Variant "{self.id}" did not all pass. Refer to logs for details.')
        """
        VariantChecks.VariantTidPathTidMatch.run(self)

    def render(self, apply_overrides: bool = True, blueprint_id: str = None):
        """
        This function converts the object into a simplified dictionary representation for use
        in exported artifacts such as manifests. This dictionary is used as input for extensions
        using the TestCaseRender event.

        If *both* `apply_overrides` and `blueprint_id` are supplied and true,
        then any Variant overrides are applied to the resultant dictionary. Both are required
        as overrides are a Blueprint-level construct so a Blueprint ID is required to differentiate
        override applicability.
        """

        original_dict = self.dict()
        final_dict = OrderedDict()

        # using Field(alias="foo", ...) requires using the alias in the cosntructor instead of
        # the actual name
        # need to manually do aliasing here instead
        final_dict["name"] = original_dict["display_name"]

        # dictionary fields are decided based on an inclusion criteria rather than exclusion
        # NOTE: when adding new attributes to the Variant class, make sure to update this list
        top_level_includes = ["description", "platforms", "guidance", "block", "detect", "controls"]
        for include in top_level_includes:
            if include in original_dict:
                final_dict[include] = original_dict[include]

        metadata = {
            "id": self.id,
            # "isv": 1,  # required
            "tid": self.tid,
            "tactic": self.tactic,
            "x_tools": self.tools,
            "x_references": self.references,
        }

        # process overrides
        if apply_overrides and blueprint_id:
            override: VariantOverride = (
                session.query(VariantOverride)
                .filter(VariantOverride.variant_id == self.id, VariantOverride.blueprint_id == blueprint_id)
                .first()
            )
            if override:
                # doing this individually as overrides only cover a few fields
                # in the future, might do this more dynamically
                if override.references:
                    metadata["x_references"] = override.references
                if override.display_name:
                    final_dict["name"] = override.display_name
                if override.guidance:
                    final_dict["guidance"] = override.guidance

        # add groups if feature is enabled
        if global_settings.add_groups:
            # Note: For VECTR uses, you may want to leave this disabled
            #       as newer VECTR versions will retain the test case template tags
            #       when creating the user mode test case
            if len(self.groups) > 0:
                metadata["groups"] = list(set([group.name for group in self.groups]))

        # delete empty x_ metadata
        final_dict["metadata"] = copy(metadata)
        for k, v in metadata.items():
            if k.startswith("x_") and v in [None, "", [], [None], [""]]:
                del final_dict["metadata"][k]

        # optionally add MITRE D3FEND details based on TID
        if global_settings.add_d3fend:
            d3fend_list = []

            mapping_artifacts = list(get_d3fend_off_artifacts_for_tid(tid=self.tid))
            if len(mapping_artifacts) > 0:
                for artifact in mapping_artifacts:
                    countermeasures = get_d3fend_ctrm_for_artifact(artifact)

                    if len(countermeasures) > 0:
                        d3fend_list.append({artifact: list(countermeasures)})
                    else:
                        d3fend_list.append(artifact)

                """
                D3FEND metadata will be a list of offensive artifacts.
                If the artifacts have countermeasures, those will be listed
                alongside the corresponding artifact.
                Each list item will be either a string (the artifact name) 
                or a mapping of a string (the artifact name) to a list of strings (the countermeasures).
                """
                final_dict["x_d3fend"] = d3fend_list

        final_dict = dict(final_dict)

        extensions_manager.emit_event(event=EventPairs.TestCaseRender, variant=final_dict)
        return final_dict

    @classmethod
    def from_yaml(cls, y: dict, **kwargs):
        # store x_ metadata separately then pass remaining metata to constructor
        _x_metadata = {}
        if "metadata" in y:
            metadata = copy(y["metadata"])
            for k, v in metadata.items():
                if k.startswith("x_"):
                    _x_metadata[k] = v
                    del y["metadata"][k]
        else:
            y["metadata"] = {}

        # ID should be provided when loading from a file/yaml
        #   though the class will create one on init
        if "id" not in y["metadata"]:
            raise LoggedException("Variant missing ID")

        # variants have 2 names, the variant name from the file path and the display name
        #   inside the file
        y["display_name"] = y.get("name", "")
        if (name := kwargs.get("name", None)) is not None:
            y["name"] = name
            del kwargs["name"]

        o = cls(**kwargs, **y, **y["metadata"])
        setattr(o, "_x_metadata", _x_metadata)  # this is on the instance, not the db
        # TODO: not sure what to do with x_ metadata yet

        session.add(o)
        session.commit()
        return o

    @classmethod
    def from_file(cls, filepath: StrOrPath):
        path = resolve_str_or_path(filepath)
        version = int(path.stem[1:])
        name = path.parent.name
        variant = cls.from_yaml(load_yaml_from_file(path), version=version, name=name, filepath=filepath.as_posix())
        return variant


class Blueprint(SQLModel, table=True):
    """
    Blueprints define the collection of all Variants and the campaigns they reside in.
    They can also, optionally, define group metadata based on technique IDs.

    The hierarchy of classes is as follows:
        Blueprint
        \_ Campaign 1
           \_ Variant 1
        \_ Campaign 2
           \_ Variant 2

    SQLAlchemy relationships are defined such that you should be able to go from
    any tier in the hierarchy to another other tier by traversing through the intermediary
    tiers. E.g. you can go from Bluepint -> Variant via Blueprint.child_campaigns[...].variants[...]
    """

    id: str = uuid_field()

    # core fields
    name: str
    description: str
    sources: OptionalStrList = str_list_field()

    # metadata
    prefix: str
    assessment: str

    # one to many with groups
    child_groups: List["BlueprintGroup"] = Relationship(back_populates="blueprint")
    # one to many with campaigns
    child_campaigns: List["BlueprintCampaign"] = Relationship(back_populates="blueprint")

    _loaded_flag: bool = PrivateAttr(default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._loaded_flag = False

    @property
    def variants(self) -> List[Variant]:
        return [variant for campaign in self.child_campaigns for variant in campaign.variants]

    @classmethod
    def from_yaml(cls, y: dict):
        metadata = {}
        if "metadata" in y:
            if "id" in y["metadata"]:
                metadata = {**metadata, **{"id": y["metadata"]["id"]}}

            # TODO: should have some event similar to render but for other export types
            #       then can hook that event in the vectr extension
            if "vectr" in y["metadata"]:
                metadata = {**metadata, **y["metadata"]["vectr"]}
            del y["metadata"]

        blueprint = cls(**y, **metadata)
        session.add(blueprint)

        # groups set in the blueprint are processed at the database level regardless
        # of the add_groups global settings
        # the add_groups settings *only* covers test cases rendering
        if "groups" in y:
            for group_name, tids in y["groups"].items():
                for tid in tids:
                    group = BlueprintGroup(name=group_name, tid=tid, blueprint=blueprint)
                    session.add(group)

        if "campaigns" in y:
            for campaign_name, block in y["campaigns"].items():
                campaign = BlueprintCampaign(name=campaign_name, blueprint=blueprint)
                session.add(campaign)

                for tid, variant_details in block.items():
                    for variant_name, variant_block in variant_details.items():
                        # variant_block can be one of the following three forms:
                        #   - integer -> ex: 1
                        #   - string  -> ex: 1;2
                        #   - dict    -> ex: { ... }
                        #
                        # the string form allows for multiple version of the same variant
                        # this has to be done like this to avoid duplicate keys in YAML
                        #
                        # the dict form is a blueprint-level override that lets the
                        # blueprint override certain fields in a variant

                        do_override = False
                        if type(variant_block) in [str, int]:
                            versions = str(variant_block)
                            if ";" in versions:
                                versions = [version.strip() for version in versions.split(";")]
                            else:
                                versions = [versions]
                        else:
                            do_override = True
                            versions = [variant_block.get("version")]

                        for version in versions:
                            try:
                                variant = lookup_variant(tid=tid, name=variant_name, version=version)
                            except Exception as e:
                                logger.error(e)
                                continue

                            session.add(variant)
                            session.add(campaign)
                            campaign.variants.append(variant)

                            if do_override:
                                override = VariantOverride(
                                    referencces=variant_block.get("references", None),
                                    guidance=variant_block.get("guidance", None),
                                    display_name=variant_block.get("name", None),
                                    variant=variant,
                                    blueprint_id=blueprint.id,
                                    campaign_id=campaign.id,
                                )
                                session.add(override)

                            # handle blueprint-level groups based on matching tid+blueprint
                            group_matches = (
                                session.query(BlueprintGroup)
                                .filter(BlueprintGroup.tid == tid, BlueprintGroup.blueprint_id == blueprint.id)
                                .all()
                            )
                            variant.groups.extend(group_matches)

        session.commit()
        blueprint.emit_loaded()
        return blueprint

    @classmethod
    def from_file(cls, filepath: StrOrPath):
        return cls.from_yaml(load_yaml_from_file(filepath))

    def emit_loaded(self):
        """
        manually triggers the loaded event emissions
        should only trigger once (per-instance)
        """
        if not self._loaded_flag:
            extensions_manager.emit_event(event=EventPairs.BlueprintLoaded, blueprint=self)
            self._loaded_flag = True


class BlueprintGroup(SQLModel, table=True):
    """
    Blueprint-level group
    """

    id: str = uuid_field()
    name: str
    tid: str

    # one to many with blueprints
    blueprint_id: Optional[str] = Field(default=None, foreign_key="blueprint.id")
    blueprint: Optional["Blueprint"] = Relationship(back_populates="child_groups")
    # many to many with variants
    variants: List["Variant"] = Relationship(back_populates="groups", link_model=VariantGroupLink)


class BlueprintCampaign(SQLModel, table=True):
    """
    Campaigns are containers of one or more Variants
    """

    id: str = uuid_field()
    name: str

    # one to many with blueprints
    blueprint_id: Optional[str] = Field(default=None, foreign_key="blueprint.id")
    blueprint: Optional["Blueprint"] = Relationship(back_populates="child_campaigns")
    # many to many with variants
    variants: List["Variant"] = Relationship(back_populates="campaigns", link_model=VariantCampaignLink)


class VariantOverride(SQLModel, table=True):
    references: OptionalStrList = str_list_field()
    guidance: OptionalStrList = str_list_field()
    display_name: str

    # pk = (variant id, blueprint id, campaign id)
    variant_id: Optional[str] = Field(default=None, foreign_key="variant.id", primary_key=True)
    variant: Variant = Relationship(back_populates="overrides")
    blueprint_id: Optional[str] = Field(default=None, foreign_key="blueprint.id", primary_key=True)
    campaign_id: Optional[str] = Field(default=None, foreign_key="blueprintcampaign.id", primary_key=True)


class LinkedDataTarget(CaseInsensitiveEnum):
    """
    Supported target types for the linked data table.
    Target types specify the object type the foreign key refers to
    """

    Variant = auto()
    Blueprint = auto()


class LinkedDataFormat(CaseInsensitiveEnum):
    """
    Supported data formats for the linked data table
    Note: the data will always be text but this format
        is used to indicate how to display it properly
    For example, if the format is 'Markdown', your
        application can render it in a Markdown box
    """

    Plaintext = auto()
    Markdown = auto()
    # reStructuredText = auto()
    YAML = auto()
    JSON = auto()
    Unformatted = auto()  # do nothing


class LinkedData(SQLModel, table=True):
    id: int = Field(primary_key=True)
    variant_id: str = Field(foreign_key="variant.id", nullable=True)
    blueprint_id: str = Field(foreign_key="blueprint.id", nullable=True)
    target_type: LinkedDataTarget = Field(sa_column=Column(SAEnum(LinkedDataTarget)))
    data_format: LinkedDataFormat = Field(sa_column=Column(SAEnum(LinkedDataFormat)))
    data: str  # data from origin
    origin: str  # identifier for origin (e.g. an extension/script)
    display_name: str  # friendly name for use by other consumers

    def __post_init__(self):
        if self.variant_id is None and self.blueprint_id is None:
            raise Exception("Variant ID and Blueprint ID for linked data cannot both be null")

    # these two relationships are implemented as property methods
    # in order to support linkeddata users storing rows with invalid
    # variant/blueprint IDs (no validation is done on IDs existing)

    @property
    def variant(self) -> Optional[Variant]:
        if variant := session.query(Variant).filter(Variant.id == self.variant_id).first():
            return variant
        else:
            return

    @property
    def blueprint(self) -> Optional[Blueprint]:
        if blueprint := session.query(Blueprint).filter(Blueprint.id == self.blueprint_id).first():
            return blueprint
        else:
            return


# sqlite requires *2* starting slashes for absolute paths...
if global_settings.db_file_path and not global_settings.db_file_path.startswith("//"):
    # autodelete is useful if you dont want to worry about schema changes
    if global_settings.db_file_autodelete:
        resolve_str_or_path(global_settings.db_file_path).unlink(missing_ok=True)

    global_settings.db_file_path = f"/{global_settings.db_file_path}"

engine = create_engine(f"sqlite://{global_settings.db_file_path}")
SQLModel.metadata.create_all(engine)
session_factory = sessionmaker(bind=engine, expire_on_commit=False)
Session = scoped_session(session_factory)
"""
This library uses a single session object for all database operations. 
If you need to perform a database operation, just import the `session` from this file.

All code in this library is fully synchronous so there should never be more than one write 
happening at a time.
"""
session = Session()


TableT = TypeVar("TableT", bound=SQLModel)


def create_single_table(table: type(TableT)):
    SQLModel.metadata.create_all(bind=engine, tables=[table])


def create_all_tables():
    # note: you should be fine to call create_all multiple times as it will not
    #       truncate an existing table on subsequent invocations
    #
    # extension developers should call this if their extension uses a table
    SQLModel.metadata.create_all(engine)


def ingest_variants_from_library(paths: List[StrOrPath]):
    """
    Load Variants from one or more library paths into the database
    """
    exceptions = False
    for path in paths:
        path = resolve_str_or_path(path)
        for variant_file in path.rglob("*.yml"):
            try:
                Variant.from_file(variant_file)
            except Exception as e:
                logger.error(f"{variant_file.as_posix()}: {e}")
                exceptions = True
    if exceptions:
        raise LoggedException("Errors encountered when loading Variants from library(s)")


def init_db(variants_paths: List[StrOrPath]):
    ingest_variants_from_library(paths=variants_paths)


def lookup_variant(tid: str, name: str, version) -> Variant:
    """
    Variant entries are identified by three pieces of information:
    - TID: MITRE ATT&CK technique ID
    - Variant name*: a friendly name for referring to all versions of a variant
    - Version: The version of the given variant
    Together, the entry is stored at the path <tid>/<name>/<version>.yml
    When the library is init'd, the files paths are split and stored based on this assumption

    *Note that the variant has two names. One name is used by the
    variant _file_ path and the other is the display name _within_ the file.
    As an example, a variant might be stored at `techniques/T1000/foo/v1.yml`
    So the name would be `foo`. Within that file it will also have
    a YAML key of `name`. The former is the name and the latter is the
    display name. The (file path) name is used for lookups.
    """
    results = (
        session.query(Variant).filter(Variant.name == name, Variant.version == int(version), Variant.tid == tid).all()
    )

    # should be exactly one result
    if len(results) > 1:
        raise LoggedException(f'Duplicate variants for version "{version}" of variant "{name}" ("{tid}")')
    if len(results) < 1:
        raise LoggedException(f'Could not locate version "{version}" of variant "{name}" ("{tid}")')
    else:
        return results[0]


from .extension import extensions_manager, EventPairs

extensions_manager.emit_event(event=EventPairs.DbReady)
# the LinkTableReady event should be called _after_ data is initially loaded into the library
# (otherwise extensions may not be able to link data to variants/blueprints)
#   and by the program that plans to use it (e.g. a script)
#   example: script inits db -> loads variants -> emits LinkTableReady
#            -> now extensions can populate the table
#            -> -> then the script can read from the table
# extensions_manager.emit_event(event=EventPairs.LinkTableReady)

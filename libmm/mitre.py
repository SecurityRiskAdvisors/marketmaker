from importlib.resources import path as resource_path
from functools import lru_cache
from dataclasses import dataclass, field, asdict
from abc import abstractmethod, ABC
from stix2 import MemoryStore, Filter
from copy import deepcopy

from .type import Set, List, TypeVar, StrSetOrList
from .utils import strip_strlist, COLORS, load_json_from_file, deep_get


"""
relies on several local data files generated with the Makefile
- "d3fend.json" is the D3FEND full mappings json from https://d3fend.mitre.org/resources/ontology/
- "enterprise.json" is the Enterprise ATT&CK JSON export from the public GitHub https://github.com/mitre/cti
- "tids.txt" is a newline-delimited list of all valid technique IDs
"""


@lru_cache(maxsize=None)
def get_cti_tids() -> Set[str]:
    """return a list of technique IDs from MITRE CTI (stored locally)"""
    with resource_path("libmm", "data") as p:
        p = p / "tids.txt"
        tids = p.read_text().split("\n")
    return set(strip_strlist(tids))


@lru_cache(maxsize=None)
def get_cti_store() -> MemoryStore:
    """returns a STIX memory store for the loaded CTI data for use in querying"""

    # the MemoryStore has definitely caused some performance issues in the past so be mindful
    # when calling methods that use this cti store
    src = MemoryStore()
    with resource_path("libmm", "data") as p:
        p = p / "enterprise.json"
        src.load_from_file(p.resolve().as_posix())
    return src


@lru_cache(maxsize=None)
def get_mitre_tactic_id_map() -> dict:
    """return a mapping of tactic name -> tactic id"""
    results = get_cti_store().query(
        [Filter("type", "=", "x-mitre-tactic"), Filter("external_references.source_name", "=", "mitre-attack")]
    )
    mapping = {}
    for result in results:  # type: dict
        tactic_id = list(filter(lambda x: x["source_name"] == "mitre-attack", result["external_references"]))[0][
            "external_id"
        ]
        tactic_name = result["name"]
        mapping[tactic_name] = tactic_id
    return mapping


@lru_cache(maxsize=None)
def get_tactic_name_by_id(tactic_id: str) -> str:
    return list(filter(lambda t: t[1] == tactic_id, get_mitre_tactic_id_map().items()))[0][0]


@lru_cache(maxsize=None)
def get_valid_tactic_ids_for_tid(tid: str) -> List[str]:
    """given a TID, return valid tactics the TID is mapped to"""
    results = get_cti_store().query(
        [
            Filter("type", "=", "attack-pattern"),
            Filter("kill_chain_phases.kill_chain_name", "=", "mitre-attack"),
            Filter("external_references.external_id", "=", tid),
        ]
    )
    tactic_names = [reference.phase_name for results in results for reference in results.kill_chain_phases]
    tactic_ids = []
    for tactic_name in tactic_names:  # type: str
        # need to reformat names before lookup as they are stored w/o space and lowercased
        tactic_name = tactic_name.replace("-", " ").title()
        tactic_name = tactic_name.replace("And", "and")
        tactic_ids.append(get_mitre_tactic_id_map()[tactic_name])
    return tactic_ids


@lru_cache(maxsize=None)
def get_d3fend_json() -> dict:
    """return the loaded D3FEND mapping data"""
    with resource_path("libmm", "data") as p:
        p = p / "d3fend.json"
        json = load_json_from_file(p)
    return json


@lru_cache(maxsize=None)
def get_d3fend_bindings() -> List[dict]:
    """returns the mapping portion of the D3FEND data that covers ATT&CK<->D3FEND"""
    return deep_get(get_d3fend_json(), ["results", "bindings"])


@lru_cache(maxsize=None)
def get_d3fend_off_artifacts_for_tid(tid: str) -> Set[str]:
    """given an ATT&CK tid, return the mapped D3FEND offensive artifacts"""
    # jq '.results.bindings[] | select(.off_tech.value =="http://d3fend.mitre.org/ontologies/d3fend.owl#T1546.013") | .off_artifact.value ' d3fend-full-mappings.json  | sort -u
    all_bindings: List[dict] = get_d3fend_bindings()
    bindings = list(
        filter(
            lambda x: deep_get(x, ["off_tech", "value"]) == f"http://d3fend.mitre.org/ontologies/d3fend.owl#{tid}",
            all_bindings,
        )
    )
    artifacts = [deep_get(binding, ["off_artifact", "value"]) for binding in bindings]
    artifacts = [f"d3f:{artifact.split('#')[-1]}" for artifact in artifacts]
    return set(artifacts)


@lru_cache(maxsize=None)
def get_d3fend_ctrm_for_artifact(artifact: str) -> Set[str]:
    """d3fend artifat -> countermeasures of specific types"""
    if artifact.startswith("d3f:"):
        artifact = artifact.replace("d3f:", "")

    allows_rel_types = ["blocks", "deletes", "detects", "disables", "evicts", "filters", "isolates", "terminates"]
    all_bindings: List[dict] = get_d3fend_bindings()
    bindings = list(
        filter(
            lambda x: deep_get(x, ["off_artifact", "value"])
            == f"http://d3fend.mitre.org/ontologies/d3fend.owl#{artifact}"
            and deep_get(x, ["def_artifact_rel_label", "value"]) in allows_rel_types,
            all_bindings,
        )
    )
    ctrms = [deep_get(binding, ["def_tech", "value"]) for binding in bindings]
    ctrms = [f"d3f:{ctrm.split('#')[-1]}" for ctrm in ctrms]
    return set(ctrms)


class LayerColors:
    LEFT = COLORS.BLUE
    RIGHT = COLORS.RED
    SHARED = COLORS.PURPLE


@dataclass
class NavLayer(ABC):
    name: str
    description: str

    @abstractmethod
    def to_json(self) -> dict:
        pass


NavLayerT = TypeVar("NavLayer", bound=NavLayer)


def _process_tid_to_technique(
    tids: StrSetOrList, cti_tids: Set[str], parent_opts: dict = None, child_opts: dict = None
) -> List[dict]:
    """transforms the given TIDs into the appropriate JSON structure for use in a Navigator Layer
    if the TID is a subtechnique (TID contains "."), then the parent TID is enabled
    this is meant to make viewing only the selected TIDs in the layer easier by
    collapsing all other parent TIDs by default
    """
    child_opts = {} if child_opts is None else child_opts
    parent_opts = {} if parent_opts is None else parent_opts

    techniques = []
    for tid in tids:
        parent_tid = tid.split(".")[0] if "." in tid else None
        if parent_tid:
            techniques.append({**parent_opts, "techniqueID": parent_tid, "showSubtechniques": True})
            cti_tids.discard(parent_tid)
        techniques.append({**child_opts, "techniqueID": tid})
        cti_tids.discard(tid)
    return techniques


def tids_to_layer_dicts(tids: List[str], *args, **kwargs) -> List[dict]:
    # given a list of TIDs, create the navlayer technique dicts
    #
    # this method will enable only the provided TIDs and their parents
    #   and disable all others in order to make use in the Navigator app
    #   easier (e.g. you can hide all disabled items)
    cti_tids = deepcopy(get_cti_tids())
    techniques = _process_tid_to_technique(tids=tids, cti_tids=cti_tids, *args, **kwargs)

    for cti_tid in cti_tids:
        techniques.append({"techniqueID": cti_tid, "enabled": False})

    return techniques


def merged_tids_to_layer_dicts(tids1: List[str], tids2: List[str]) -> List[dict]:
    """given two lists of tids, create a merged list and colorize the lists differently based on overlap"""
    cti_tids = deepcopy(get_cti_tids())
    techniques = []

    set1 = set(tids1)
    set2 = set(tids2)
    left, right, shared = set1.difference(set2), set2.difference(set1), set1.intersection(set2)
    techniques.extend(_process_tid_to_technique(tids=left, cti_tids=cti_tids, child_opts={"color": LayerColors.LEFT}))
    techniques.extend(_process_tid_to_technique(tids=right, cti_tids=cti_tids, child_opts={"color": LayerColors.RIGHT}))
    techniques.extend(
        _process_tid_to_technique(tids=shared, cti_tids=cti_tids, child_opts={"color": LayerColors.SHARED})
    )

    for cti_tid in cti_tids:
        techniques.append({"techniqueID": cti_tid, "enabled": False})

    return techniques


@dataclass
class NavLayerV44(NavLayer):
    # Navgiator layer version 4.4 per https://github.com/mitre-attack/attack-navigator/blob/master/layers/LAYERFORMATv4_4.md
    # implements only the bare minimum fields required for use in the Navigator app
    techniques: List[dict] = field(default_factory=list)
    layout: dict = field(default_factory=lambda: {"layout": "flat"})
    domain: str = "enterprise-attack"
    selectTechniquesAcrossTactics: bool = False
    selectSubtechniquesWithParent: bool = False

    def __post_init__(self):
        self._tids = []

    @property
    def tid_list(self) -> List[str]:
        return self._tids

    def set_tids(self, tids: List[str]) -> "NavLayerV44":  # cascades
        self._tids = tids
        self.techniques = tids_to_layer_dicts(tids=tids, child_opts={"color": LayerColors.SHARED})
        # sort by technique ID
        self.techniques = sorted(self.techniques, key=lambda x: x["techniqueID"])
        return self

    def to_json(self) -> dict:
        return asdict(self)


def generate_navlayer_v44(name: str, description: str, tids: List[str]) -> NavLayerT:
    """returns nav layer v4.4 for given TIDs"""
    return NavLayerV44(name=name, description=description).set_tids(tids=tids)


def generate_latest_navlayer(*args, **kwargs) -> NavLayerT:
    """alias method for latest nav layer version implemented"""
    return generate_navlayer_v44(*args, **kwargs)


def generate_comparison_navlayer_v44(left_layer: NavLayerT, right_layer: NavLayerT):
    """Creates a merged layer from two layers that can be used for comparison purposes
    TIDs in only the left layer are colored blue. TIDs in only the right layer are colored red.
    TIDs in both layers are colored purple.
    """
    merged_layer = NavLayerV44(
        name="Comparison Layer", description=f"Comparison between {left_layer.name} and {right_layer.name}"
    )
    # generate an empty base layer
    merged_layer_json = merged_layer.to_json()

    # add merged techniques in proper format and a legend
    merged_layer_json_updates = {
        "techniques": merged_tids_to_layer_dicts(tids1=left_layer.tid_list, tids2=right_layer.tid_list),
        "legendItems": [
            {"label": "left/first", "color": LayerColors.LEFT},
            {"label": "right/second", "color": LayerColors.RIGHT},
            {"label": "shared", "color": LayerColors.SHARED},
        ],
    }

    return {**merged_layer_json, **merged_layer_json_updates}


def generate_latest_comparison_layer(*args, **kwargs) -> dict:
    """alias method for latest merged layer version implemented"""
    return generate_comparison_navlayer_v44(*args, **kwargs)

import csv
import io
import shutil
from enum import auto

from .type import StrOrPath, List
from .utils import resolve_str_or_path, dump_yaml_to_file, compare_set_overlap, deep_get
from .mitre import generate_latest_navlayer, generate_latest_comparison_layer
from .sql import Blueprint, BlueprintCampaign


class BlueprintExport:
    Manifest = auto()
    NavigatorLayer = auto()
    SummaryCsv = auto()
    Sublibrary = auto()


class ComparisonExport:
    NavigatorLayer = auto()
    OverlapByMitre = auto()
    OverlapByVariant = auto()


"""
Manifests are the output plan files. 
They are essentially a hydrated version of the Blueprint and 
are subject to Variant rendering modification.

Sublibraries are library-like directories of the Variants present in the Blueprint. 
However, they cannot be used as input for a Blueprint as the directory structure differs.
Additionally, the Variants are the rendered form, not the original form.
Sublibraries are intended to be used when you need to share test plan as individual items instead 
of - or in addition to - a complete plan file.
"""


def gen_manifest_from_campaigns(campaigns: List[BlueprintCampaign], prefix: str, bundle: str) -> dict:
    metadata = {"metadata": {"prefix": prefix, "bundle": bundle}}
    campaign_dict = {}
    for campaign in campaigns:
        campaign_dict[campaign.name] = []
        for variant in campaign.variants:
            campaign_dict[campaign.name].append(
                variant.render(apply_overrides=True, blueprint_id=campaign.blueprint_id)
            )
    # TODO: campaigns will eventually be moved under a top-level key of their own
    #       in the meantime, need to delete any campaigns called "metadata" to prevent overlap
    if "metadata" in campaign_dict:
        del campaign_dict["metadata"]
    # switching the order of these obviates the above key del,
    # but it unfortunately puts the metadata at the bottom of the file
    return {**metadata, **campaign_dict}


def gen_manifest_from_blueprint(blueprint: Blueprint) -> dict:
    return gen_manifest_from_campaigns(
        campaigns=blueprint.child_campaigns, prefix=blueprint.prefix, bundle=blueprint.assessment
    )


def gen_navlayer_from_blueprint(blueprint: Blueprint):
    tids = [variant.tid for variant in blueprint.variants]
    return generate_latest_navlayer(name=blueprint.name, description=blueprint.description, tids=tids)


def gen_navlayer_json_from_blueprint(blueprint: Blueprint) -> dict:
    return gen_navlayer_from_blueprint(blueprint=blueprint).to_json()


def gen_summary_csv_from_blueprint(blueprint: Blueprint) -> str:
    out_str = io.StringIO()
    summary = csv.writer(out_str, quoting=csv.QUOTE_ALL)
    summary.writerow(["Test Case", "MITRE ID", "Campaign", "Description"])
    for campaign in blueprint.child_campaigns:
        for variant in campaign.variants:
            rendered = variant.render(apply_overrides=True, blueprint_id=blueprint.id)
            tid = deep_get(rendered, ["metadata", "tid"])
            summary.writerow([rendered.get("name"), tid, campaign.name, rendered.get("description")])

    out_str.seek(0)
    summary_str = out_str.read()
    out_str.close()
    return summary_str


def gen_sublibrary(root: StrOrPath, blueprint: Blueprint):
    root = resolve_str_or_path(root)

    def rmtree_callback(function, path, excinfo):
        # excinfo = (error class, error, traceback)
        if excinfo[0] == FileNotFoundError:
            pass
        else:
            raise excinfo[1]

    shutil.rmtree(root, onerror=rmtree_callback)
    for campaign in blueprint.child_campaigns:
        for variant in campaign.variants:
            campaign_name_stripped = campaign.name.replace(" ", "").replace(".", "")
            campaign_root = root / campaign_name_stripped
            variant_file_name = f"{variant.id}.yml"
            variant_file_path = campaign_root / variant_file_name
            variant_file_path.parent.mkdir(exist_ok=True, parents=True)
            dump_yaml_to_file(
                yaml_=variant.render(apply_overrides=True, blueprint_id=campaign.blueprint_id),
                yaml_file=variant_file_path,
            )


def gen_comparison_navlayer_json_from_blueprints(blueprint1: Blueprint, blueprint2: Blueprint) -> dict:
    return generate_latest_comparison_layer(
        left_layer=gen_navlayer_from_blueprint(blueprint=blueprint1),
        right_layer=gen_navlayer_from_blueprint(blueprint=blueprint2),
    )


def gen_overlap_by_mitre_from_blueprints(blueprint1: Blueprint, blueprint2: Blueprint) -> float:
    source_set = set([(variant.tactic, variant.tid) for variant in blueprint1.variants])
    target_set = set([(variant.tactic, variant.tid) for variant in blueprint2.variants])
    return compare_set_overlap(source_set, target_set)


def gen_overlap_by_variant_from_blueprints(blueprint1: Blueprint, blueprint2: Blueprint) -> float:
    source_set = set([(variant.name, variant.tid) for variant in blueprint1.variants])
    target_set = set([(variant.name, variant.tid) for variant in blueprint2.variants])
    return compare_set_overlap(source_set, target_set)


BLUEPRINT_EXPORTS_SWITCH = {
    BlueprintExport.Manifest: gen_manifest_from_blueprint,
    BlueprintExport.NavigatorLayer: gen_navlayer_json_from_blueprint,
    BlueprintExport.SummaryCsv: gen_summary_csv_from_blueprint,
    BlueprintExport.Sublibrary: gen_sublibrary,
}

COMPARISON_EXPORTS_SWITCH = {
    ComparisonExport.NavigatorLayer: gen_comparison_navlayer_json_from_blueprints,
    ComparisonExport.OverlapByMitre: gen_overlap_by_mitre_from_blueprints,
    ComparisonExport.OverlapByVariant: gen_overlap_by_variant_from_blueprints,
}


def gen_blueprint_export(blueprint: Blueprint, export_type: Blueprint, **fn_kwargs):
    fn = BLUEPRINT_EXPORTS_SWITCH.get(export_type)
    return fn(blueprint=blueprint, **fn_kwargs)


def gen_comparison_export(blueprint1: Blueprint, blueprint2: Blueprint, export_type: BlueprintExport, **fn_kwargs):
    fn = COMPARISON_EXPORTS_SWITCH.get(export_type)
    return fn(blueprint1=blueprint1, blueprint2=blueprint2, **fn_kwargs)

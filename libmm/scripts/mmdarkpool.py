import click
import pathlib
import jinja2
import shutil
from functools import lru_cache
import inspect
from stix2 import AttackPattern

from libmm.config import global_settings
from libmm.log import logger
from libmm.sql import init_db, Variant, Blueprint, session, LinkedData, LinkedDataFormat, LinkedDataTarget
from libmm.extension import extensions_manager, EventPairs
from libmm.utils import load_json_from_file, dump_yaml_to_file, dump_json_to_file
from libmm.type import List, Tuple, Optional
from libmm.scripts.shared import SharedOptions, validate_multi_directory
from libmm.index import gen_blueprint_export, BlueprintExport
from libmm.mitre import get_cti_store, Filter

global_settings.run_checks = False

LatestBlueprintPair = Tuple[str, Blueprint]


# TODO:
#   download button for linked content that is not intended for viewing (e.g. a binary)
#   probably need new linked data format or column for downloadable content
#   also needs to get create directory in web root for storage


def lookup_technique_by_tid(tid: str) -> Optional[List[AttackPattern]]:
    return get_cti_store().query(
        [
            Filter("type", "=", "attack-pattern"),  # attack pattern = technique
            Filter("external_references.source_name", "=", "mitre-attack"),
            Filter("external_references.external_id", "=", tid),
        ]
    )


@lru_cache(maxsize=None)
def resolve_tid_to_name(value: str, parent: bool = True) -> str:
    """
    Resolve the given MITRE ATT&CK TID to its name
    If parent = True, include the parent technique's name in the returned value
        (only applies to subtechniques)

    Examples:
        T1071.001 (parent=False) -> Web Protocols
        T1071.001 (parent=True)  -> Application Layer Protocol: Web Protocols
        T1105     (parent=True)  -> Ingress Tool Transfer
            * parent here has no effect since this TID is not a subtechnique

    If the TID cannot be resolved, it is returned back as-is

    This function is intended to be used as a Jinja filter and is exposed as 'tid2name'
    """
    technique = lookup_technique_by_tid(value)
    if len(technique) == 1:
        technique_name = technique[0].name
        final_name = technique_name

        if parent and "." in value:
            parent_tid = value.split(".")[0]
            parent_technique = lookup_technique_by_tid(parent_tid)

            # if you can resolve the base tid but not the parent, return the resolved base
            # and ignore the issue with parent
            if len(parent_technique) == 1:
                parent_name = parent_technique[0].name
                final_name = f"{parent_name}: {final_name}"

        return final_name

    else:
        return value


tpl_path = pathlib.Path(__file__).parent / "mmdarkpool" / "templates"
jinja_loader = jinja2.FileSystemLoader(searchpath=tpl_path)
jinja_env = jinja2.Environment(loader=jinja_loader)
# add custom filters to template loader
jinja_env.filters["tid2name"] = resolve_tid_to_name


class Templates:
    """
    Jinja template names
    """

    Variant = "variant.html.j2"
    Variants = "variants.html.j2"
    Blueprint = "blueprint.html.j2"
    Blueprints = "blueprints.html.j2"


# paths have no leading slashes so they dont conflict with pathlib path merging
# e.g. /abc + /def = /def


class StaticDirectories:
    Variants = "testcases"
    Blueprints = "bundles"
    Manifests = "manifests"
    NavigatorLayers = "layers"
    NavigatorUI = "navigator"
    Addons = "addons"


class SitePaths:
    Blueprints = "bundles.html"
    Variants = "testcases.html"
    Index = "index.html"
    NavigatorIndex = StaticDirectories.NavigatorUI + "/index.html"

    Variant = StaticDirectories.Variants + "/{variant_id}.html"
    Blueprint = StaticDirectories.Blueprints + "/{blueprint_id}.html"
    BlueprintDir = StaticDirectories.Blueprints + "/{blueprint_id}"
    BlueprintVariant = StaticDirectories.Blueprints + "/{blueprint_id}/{variant_id}.html"
    NavigatorLayer = StaticDirectories.NavigatorLayers + "/{blueprint_id}.json"
    BlueprintRta = StaticDirectories.Addons + "/rta/{blueprint_id}.py"
    Manifest = StaticDirectories.Manifests + "/{blueprint_id}.yml"


def format_linked_data(linked_data: LinkedData):
    """
    Given a LinkedData instance, apply HTML formatting based
    on the format
    Markdown will be rendered client-side
    YAML/JSON will have syntax highlighting applied client-side
    """

    data = linked_data.data
    if linked_data.data_format == LinkedDataFormat.Plaintext:
        data = f"<pre>{data}</pre>"
    elif linked_data.data_format == LinkedDataFormat.Markdown:
        data = f"<div id='markdown'>{data}</div>"
    elif linked_data.data_format in [LinkedDataFormat.YAML, LinkedDataFormat.JSON]:
        data = f"<pre><code>{data}</code><pre>"
    elif linked_data.data_format == LinkedDataFormat.Unformatted:
        pass

    return data


def render_variant_listing(variants: List[Variant]):
    """
    vars:
    - all_variants
    """
    return jinja_env.get_template(Templates.Variants).render(all_variants=variants)


def render_blueprint_listing(latest_blueprints: List[LatestBlueprintPair], all_blueprints: List[Blueprint]):
    """
    vars:
    - latest_blueprints
    - all_blueprints
    """
    return jinja_env.get_template(Templates.Blueprints).render(
        latest_blueprints=latest_blueprints, all_blueprints=all_blueprints
    )


def render_blueprint(
    latest_blueprints: List[LatestBlueprintPair], all_blueprints: List[Blueprint], blueprint: Blueprint
):
    """
    vars:
    - latest_blueprints
    - all_blueprints
    - blueprint
    """
    linked_data = {}
    for row in (
        session.query(LinkedData)
        .filter(LinkedData.blueprint_id == blueprint.id, LinkedData.target_type == LinkedDataTarget.Blueprint)
        .all()
    ):  # type: LinkedData
        data = format_linked_data(row)
        linked_data.setdefault(row.display_name, []).append(data)
    return jinja_env.get_template(Templates.Blueprint).render(
        latest_blueprints=latest_blueprints, all_blueprints=all_blueprints, blueprint=blueprint, linked_data=linked_data
    )


def render_variant(variant: Variant, **kwargs):
    """
    vars
    - variant
    other vars
    - blueprint (if included, adds sidebar for campaigns)
    """

    linked_data = {}
    for row in (
        session.query(LinkedData)
        .filter(LinkedData.variant_id == variant.id, LinkedData.target_type == LinkedDataTarget.Variant)
        .all()
    ):  # type: LinkedData
        data = format_linked_data(row)
        linked_data.setdefault(row.display_name, []).append(data)

    # cleanup guidance
    final_guidance = ""
    if variant.guidance:
        for guidance in variant.guidance:
            guidance = guidance.strip()
            if "\n" in guidance:
                guidance = "\n".join([g.strip() for g in guidance.split("\n")])
            if len(guidance) > 0 and guidance not in [None, "", "\n"]:
                final_guidance += guidance
                final_guidance += "\n"

    # left-side menu is default all other variants in library that share a TID/
    #   if blueprint is provided, the left-side menu is all variants in that blueprint
    #   grouped by the campaign name
    return jinja_env.get_template(Templates.Variant).render(
        variant=variant,
        related_variants=session.query(Variant).filter(Variant.tid == variant.tid).all(),
        linked_data=linked_data,
        guidance=final_guidance,
        mitre_description=lookup_technique_by_tid(variant.tid)[0].description,
        **kwargs,
    )


def render_blueprint_variant(blueprint: Blueprint, **kwargs):
    """
    vars:
    - blueprint (optional, None->no sidebar)
    - variant
    - prerequisites (human-readable) & platforms
        - as jinja filter function
    - operator_guidance (rendered
    """
    return render_variant(blueprint=blueprint, **kwargs)


@click.group()
@click.version_option(message="version: %(version)s")
def main():
    logger.info(f"Global settings resolved to: {global_settings.json()}")
    pass


blueprints_opt = click.option(
    "-b",
    "--blueprint-paths",
    "blueprint_paths",
    type=str,
    help="One or more paths to blueprint directories. Concatenate paths with a ':'. For example: /foo:/bar. Defaults to 'blueprints/'",
    callback=validate_multi_directory,
    required=True,
    default="indexes/",
)

navdir_opt = click.option(
    "-n",
    "--nav-directory",
    "nav_directory",
    help="MITRE ATT&CK Navigator bundle directory",
    type=click.Path(resolve_path=True, file_okay=False, exists=True, writable=True),
    required=True,
)

recurse_opt = click.option(
    "-r",
    "--recurse",
    "recurse",
    help="Recurse through Blueprints directory. Defaults to false",
    is_flag=True,
    default=False,
    required=False,
)


@click.command(name="html")
@SharedOptions.techniques
@blueprints_opt
@SharedOptions.infile("latest", "latest-json", "Path to latest.json file")
@SharedOptions.outdir("outdir", "output-directory", "Directory to output rendered HTML")
@navdir_opt
@recurse_opt
def html(techniques, blueprint_paths, latest_json, output_directory, nav_directory, recurse):
    # step 1: init data and load bps
    init_db(variants_paths=techniques)

    all_bps = []
    latest_bps: List[LatestBlueprintPair] = []  # list of (canonical name, blueprint) tuples

    # k:v of canonical name to file name
    latest_json = load_json_from_file(latest_json).get("bundles", {})
    # invert so lookup is done based on file name -> canonical name
    latest_json = {v: k for k, v in latest_json.items()}

    glob_pattern = "*.yml" if not recurse else "**/*.yml"
    for blueprint_path in blueprint_paths:
        for yaml_doc in pathlib.Path(blueprint_path).glob(glob_pattern):
            bp = Blueprint.from_file(yaml_doc)
            all_bps.append(bp)
            if yaml_doc.name in latest_json:
                latest_bps.append((latest_json[yaml_doc.name], bp))

    # sorting bps by length of descriptions so that row heights are *roughly* similar
    all_bps = sorted(all_bps, key=lambda x: len(x.description))
    latest_bps = sorted(latest_bps, key=lambda x: len(x[1].description))

    variants = session.query(Variant).all()

    # step 2: signal link table
    # TODO: most extensions start disabled and are enabled via link ready or cli start
    #       in this case bp load occurs first so those events will not trigger
    #       may need to come back to that
    extensions_manager.emit_event(event=EventPairs.LinkTableReady)

    # step 3 render pages
    output_directory: pathlib.Path
    shutil.rmtree(output_directory, ignore_errors=True)
    output_directory.mkdir(parents=True, exist_ok=False)

    # make all site directories
    for directory in [member[0] for member in inspect.getmembers(StaticDirectories) if not member[0].startswith("__")]:
        output_directory.joinpath(getattr(StaticDirectories, directory)).mkdir(exist_ok=True)

    # render all variant files + listing
    output_directory.joinpath(SitePaths.Variants).write_text(render_variant_listing(variants=variants))
    for variant in variants:
        variant_file = SitePaths.Variant.format(variant_id=variant.id)
        output_directory.joinpath(variant_file).write_text(render_variant(variant=variant))

    # render all blueprint files + listing
    output_directory.joinpath(SitePaths.Blueprints).write_text(
        render_blueprint_listing(all_blueprints=all_bps, latest_blueprints=latest_bps)
    )
    for blueprint in all_bps:
        blueprint_file = SitePaths.Blueprint.format(blueprint_id=blueprint.id)
        output_directory.joinpath(blueprint_file).write_text(
            render_blueprint(all_blueprints=all_bps, latest_blueprints=latest_bps, blueprint=blueprint)
        )

        blueprint_dir = SitePaths.BlueprintDir.format(blueprint_id=blueprint.id)
        output_directory.joinpath(blueprint_dir).mkdir(exist_ok=True)
        for variant in blueprint.variants:
            blueprint_variant_file = SitePaths.BlueprintVariant.format(blueprint_id=blueprint.id, variant_id=variant.id)
            output_directory.joinpath(blueprint_variant_file).write_text(
                render_blueprint_variant(blueprint=blueprint, variant=variant)
            )

        manifest = gen_blueprint_export(blueprint=blueprint, export_type=BlueprintExport.Manifest)
        manifest_file = SitePaths.Manifest.format(blueprint_id=blueprint.id)
        dump_yaml_to_file(manifest, output_directory.joinpath(manifest_file))

        layer = gen_blueprint_export(blueprint=blueprint, export_type=BlueprintExport.NavigatorLayer)
        # patch the layer to hide disabled techniques and
        # set version to be latest (4.5) -> mm uses 4.4 but 4.5 is required
        #   to avoid getting prompted to migrate layer versions
        layer["hideDisabled"] = True
        layer["versions"] = {"layer": "4.5"}
        layer_file = SitePaths.NavigatorLayer.format(blueprint_id=blueprint.id)
        dump_json_to_file(layer, output_directory.joinpath(layer_file))

    # alias bundle listing to index
    shutil.copy(output_directory.joinpath(SitePaths.Blueprints), output_directory.joinpath(SitePaths.Index))

    # copy navigator
    shutil.copytree(nav_directory, output_directory.joinpath(StaticDirectories.NavigatorUI), dirs_exist_ok=True)
    nav_index = output_directory.joinpath(SitePaths.NavigatorIndex)
    # relocate paths to new subdirectory in nav index
    nav_index_body = (
        nav_index.read_text()
        .replace('href="', 'href="/navigator/')
        .replace('src="', 'src="/navigator/')
        .replace("//", "/")  # fixes double '/' in <base> href
    )
    nav_index.write_text(nav_index_body)


main.add_command(html)

if __name__ == "__main__":
    main()

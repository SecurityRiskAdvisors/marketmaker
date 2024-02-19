import click
import sys

from libmm.index import gen_blueprint_export, gen_comparison_export, BlueprintExport, ComparisonExport
from libmm.type import OutputPrefixes
from libmm.utils import dump_yaml_to_file, dump_json_to_file
from libmm.config import global_settings
from libmm.log import logger
from libmm.inject import opts_from_extensions
from libmm.extension import extensions_manager, EventPairs
from libmm.mitre import get_d3fend_off_artifacts_for_tid
from libmm.scripts.shared import SharedOptions
from libmm.sql import init_db, Variant, Blueprint

# TODO: command to run checks standalone


@click.group()
@click.version_option(message="version: %(version)s")
def main():
    logger.info(f"Global settings resolved to: {global_settings.json()}")
    pass


@click.command(name="generate")
@SharedOptions.techniques
@SharedOptions.blueprint(suffix=False)
@SharedOptions.outfile("o", "output", "Manifest YAML output file")
@SharedOptions.outfile("s", "summary", "Summary CSV output file")
@SharedOptions.outfile("n", "navigator", "MITRE Navigator layer output file")
@SharedOptions.outdir("i", "sublibrary", "Sublibrary directory")
@opts_from_extensions()
def generate(techniques, blueprint, output=None, summary=None, navigator=None, sublibrary=None, **kwargs):
    if all(opt is None for opt in [output, summary, navigator, sublibrary]):
        # click.echo(f"{OutputPrefixes.Bad} Minimum one output file option is required", err=True)
        # sys.exit(1)
        click.echo(f"{OutputPrefixes.Neutral} No default generation options specified")

    init_db(variants_paths=techniques)
    extensions_manager.emit_event(event=EventPairs.CliStart)

    blueprint = Blueprint.from_file(blueprint)

    click.echo(f"{OutputPrefixes.Neutral} {Variant.count()} variants in library")
    click.echo(f"{OutputPrefixes.Neutral} {len(blueprint.variants)} variants in blueprint")

    if output:
        manifest = gen_blueprint_export(blueprint, BlueprintExport.Manifest)
        dump_yaml_to_file(manifest, output)
        click.echo(f"{OutputPrefixes.Good} Wrote manifest to {output.as_posix()}")

    if navigator:
        navlayer = gen_blueprint_export(blueprint, BlueprintExport.NavigatorLayer)
        dump_json_to_file(json_=navlayer, json_file=navigator)
        click.echo(f"{OutputPrefixes.Good} Wrote navigator layer to {navigator.as_posix()}")

    if sublibrary:
        gen_blueprint_export(blueprint, BlueprintExport.Sublibrary, root=sublibrary)
        click.echo(f"{OutputPrefixes.Good} Wrote sub-library to {sublibrary.as_posix()}")

    if summary:
        csv = gen_blueprint_export(blueprint, BlueprintExport.SummaryCsv)
        summary.write_text(csv)
        click.echo(f"{OutputPrefixes.Good} Wrote summary to {summary.as_posix()}")

    extensions_manager.emit_event(event=EventPairs.CliExit)


@click.command(name="compare")
@SharedOptions.techniques
@SharedOptions.blueprint(i=1, suffix=True)
@SharedOptions.blueprint(i=2, suffix=True)
@SharedOptions.outfile("n", "navigator", "Comparison MITRE Navigator layer output file", required=False)
@click.option("--stats", help="Print stats for overlap", is_flag=True)
def compare(techniques, blueprint1, blueprint2, navigator, stats):
    if all(opt is None for opt in [navigator, stats]):
        click.echo(f"{OutputPrefixes.Bad} Minimum one output file option is required", err=True)
        sys.exit(1)

    init_db(variants_paths=techniques)
    click.echo(f"{OutputPrefixes.Neutral} {Variant.count()} variants in library")

    blueprint1 = Blueprint.from_file(blueprint1)
    click.echo(f"{OutputPrefixes.Neutral} {len(blueprint1.variants)} variants in {blueprint1.name}")

    blueprint2 = Blueprint.from_file(blueprint2)
    click.echo(f"{OutputPrefixes.Neutral} {len(blueprint2.variants)} variants in {blueprint2.name}")

    if navigator:
        layer = gen_comparison_export(blueprint1, blueprint2, ComparisonExport.NavigatorLayer)
        dump_json_to_file(json_=layer, json_file=navigator)
        click.echo(f"{OutputPrefixes.Good} Writing merged layer to {navigator.as_posix()}")

    if stats:
        entry_overlap = gen_comparison_export(blueprint1, blueprint2, ComparisonExport.OverlapByVariant)
        mitre_overlap = gen_comparison_export(blueprint1, blueprint2, ComparisonExport.OverlapByMitre)
        click.echo(f"{OutputPrefixes.Good} Stats:")
        click.echo(f" ├── Variant overlap: {round(entry_overlap*100)}%")
        click.echo(f" └── MITRE overlap: {round(mitre_overlap*100)}%")


@click.group(name="util")
def util():
    pass


@util.command(name="defend")
@click.option("-t", "--tid", required=True, help="Technique ID", type=str)
def defend(tid):
    off_artifacts = get_d3fend_off_artifacts_for_tid(tid=tid)
    artifacts_str = " / ".join(off_artifacts)
    click.echo(f'{OutputPrefixes.Good} {len(off_artifacts)} offensive artifact(s) for "{tid}": {artifacts_str}')


main.add_command(generate)
main.add_command(compare)
main.add_command(util)

if __name__ == "__main__":
    main()

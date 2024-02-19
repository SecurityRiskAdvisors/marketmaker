import pathlib
import click

from libmm.utils import resolve_str_or_path


def to_path(ctx, param, value):
    if type(value) == str:
        return resolve_str_or_path(value)
    else:
        return value


def validate_multi_directory(ctx, param, value):
    if value:
        if ":" in value:
            directories = value.split(":")
        else:
            directories = [value]

        for directory in directories:
            path = pathlib.Path(directory)
            if path.exists() and path.is_dir():
                return directories

        raise click.BadParameter("Path(s) must exist and must be directories")


class SharedOptions:
    techniques = click.option(
        "-t",
        "--technique-paths",
        "techniques",
        type=str,
        help="One or more paths to technique directories. Concatenate paths with a ':'. For example: /foo:/bar. Defaults to 'techniques/'",
        callback=validate_multi_directory,
        required=True,
        default="techniques/",
    )

    # TODO: required true/false modifiers
    @staticmethod
    def __file_option(shortname: str, longname: str, helptxt: str, path_kwargs: dict = None, **kwargs):
        return click.option(
            f"-{shortname}",
            f"--{longname}",
            help=helptxt,
            type=click.Path(resolve_path=True, **path_kwargs),
            callback=to_path,
            **kwargs,
        )

    @staticmethod
    def outfile(shortname: str, longname: str, helptxt: str = "output file", **kwargs):
        return SharedOptions.__file_option(
            shortname=shortname,
            longname=longname,
            helptxt=helptxt,
            path_kwargs={"dir_okay": False, "writable": True},
            **kwargs,
        )

    @staticmethod
    def outdir(shortname: str, longname: str, helptxt: str = "output directory", **kwargs):
        return SharedOptions.__file_option(
            shortname=shortname,
            longname=longname,
            helptxt=helptxt,
            path_kwargs={"file_okay": False, "exists": False, "writable": True},
            **kwargs,
        )

    @staticmethod
    def infile(shortname: str, longname: str, helptxt: str = "input file", **kwargs):
        return SharedOptions.__file_option(
            shortname=shortname,
            longname=longname,
            helptxt=helptxt,
            path_kwargs={"dir_okay": False, "exists": True},
            **kwargs,
        )

    @staticmethod
    def blueprint(i: int = 1, suffix: bool = False):
        # suffix = "" if i == 1 else str(i)
        suffix = str(i) if suffix else ""
        return SharedOptions.infile(
            shortname=f"b{suffix}",
            longname=f"blueprint{suffix}",
            helptxt=f"path to blueprint {suffix}",
            required=True,
        )

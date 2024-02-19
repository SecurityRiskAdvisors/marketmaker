import click
from typing import TYPE_CHECKING

from .extension import extensions_manager

if TYPE_CHECKING:
    from .extension import UserHookSetting


def cli_callback(ctx, param, value):
    # Note: cannot do this in the decorated functions as a dynamic function because the last
    #   decorated function will override whatever the setting is, preventing proper callback exec
    setting = extensions_manager.match_setting_by_cli_arg(arg=param.opts[0])
    setting.value_callback(value)
    return value


def opts_from_extensions():
    """
    Injects the CLI args defined in the registered extensions into a CLI application
    Note: this is opt-in -> CLI applications must add this as a decorator to their CLI function(s)
    """

    def inner(func):
        for extension in extensions_manager.extensions:
            for setting in extension.hook.settings:  # type: UserHookSetting
                if setting.cli_arg is not None:
                    ext_option = click.option(
                        setting.cli_arg,
                        help=f'Option added from "{extension.name}". Refer to extension documentation.',
                        required=False,
                        callback=cli_callback,
                        envvar=setting.env_var,
                        type=str,
                    )
                    ext_option(func)
        return func

    return inner

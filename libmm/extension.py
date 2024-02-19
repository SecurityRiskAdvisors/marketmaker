from dataclasses import dataclass
from abc import ABC, abstractmethod
import importlib.util
from importlib.resources import path as resource_path
import atexit
import os

from .utils import resolve_str_or_path
from .type import StrOrPath, Enum, auto, List, TypeVar, Any
from .config import global_settings
from .log import logger


class EventTypes(Enum):
    """
    Hooked events

    Events:
        `TestCaseRender`: called when render() is used during an export of a test case. For example, when generating the manifest or a sublibrary. Use this hook when you need to modify a test case or generate a related artifact.
            Example use: add additional metadata on exported variant
        `DbOjectInit` : called when a database object instance is initialized
            Example use: perform an action against all row instances
        `BlueprintLoaded` : called when after all Blueprint init/post-inits are finished
            Example use: perform an action when a blueprint is fully loaded, including relationships
        `CliExit`: Signals a CLI program exit
            Example use: Output data to terminal
        `CliStart`: Signals the start of a CLI program function.
            Example use: validate setting values
        `Init` : Signals when the extension manager is initialized
            Example use: establish connection to external resource
        `Exit` :  Signals program exits; executes via an atexit function
            Example use: Cleanup extension data/files
        `DbReady` : Signals the database tables are created and the data is ready to be used (but not necessarily that the data is loaded)
            Example use: Registger a database ORM event
        `LinkTableReady` : Signals that linked data can be added to the database
            Example use: Store additional data tied to a Variant

    Not all events are called always.
        `Init` is always called*
        `Exit` is always called* assuming exit handlers are called (e.g. Ctrl-C will cause it to fail)
        `CliStart` and `CliExit` are optionally called by CLI scripts and never main library code
        `TestCaseRender` and `IndexLoad` are always called assuming the relevant code paths are reached.
            E.g. if a test case is never exported, render() is never called.
        etc

        *Assumes extensions are enabled

    Additional notes:
    - `Init` is called before CLI arguments are injected, so you should validate user-provided values outside `Init`
    """

    # content events
    TestCaseRender = auto()
    DbOjectInit = auto()
    BlueprintLoaded = auto()

    # cli events
    CliExit = auto()
    CliStart = auto()

    # internal events
    Init = auto()
    Exit = auto()
    DbReady = auto()
    LinkTableReady = auto()


class Context:
    """
    Contexts are whats passed to consumers of an event.
    Each event type uses a potentially distinct context.
    Refer to EventPairs below for the event<->context mapping
    """

    pass


ContextT = TypeVar("ContextT", bound=Context)


@dataclass
class TestCaseRenderContext(Context):
    """
    Context for TestCaseRender event
    Notably, the variant is stored as a dict, not as a Variant object.
    This is b/c the variant is passed at the end of the render steps, after all alterations are made (e.g. removing unexportable fields)
    """

    variant: dict


@dataclass
class DbOjectInitContext(Context):
    """
    Context for DbOjectInit event
    The database object is passed after __init__
    """

    object: Any


@dataclass
class BlueprintLoadedContext(Context):
    """
    Context for BlueprintLoaded event
    The Blueprint object
    """

    blueprint: Any


@dataclass
class EmptyContext(Context):
    """
    Context for CliExit event
    No details are passed
    """

    pass


@dataclass
class EventPair:
    """Maps a context type to an event type"""

    event_type: EventTypes
    context: type(ContextT)


class EventPairs:
    TestCaseRender = EventPair(EventTypes.TestCaseRender, TestCaseRenderContext)
    DbOjectInit = EventPair(EventTypes.DbOjectInit, DbOjectInitContext)
    BlueprintLoaded = EventPair(EventTypes.BlueprintLoaded, BlueprintLoadedContext)
    CliExit = EventPair(EventTypes.CliExit, EmptyContext)
    CliStart = EventPair(EventTypes.CliStart, EmptyContext)
    Init = EventPair(EventTypes.Init, EmptyContext)
    Exit = EventPair(EventTypes.Exit, EmptyContext)
    DbReady = EventPair(EventTypes.DbReady, EmptyContext)
    LinkTableReady = EventPair(EventTypes.LinkTableReady, EmptyContext)


class AbstractUserHook(ABC):
    """

    Notes:
        - Hooks are initialized once when loaded from disk. This means any data stored with the class instance is persisted between calls to the hook() function.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def settings(self) -> List["UserHookSetting"]:
        return []

    @abstractmethod
    def hook(self, event_type: EventTypes, context):
        pass


UserHookT = TypeVar("UserHookT", bound=AbstractUserHook)


@dataclass
class UserHookSetting:
    """Container for individual setting of an extension"""

    name: str
    parent: UserHookT
    # all are optional since extensions can run w/o requiring user input
    value = None

    def value_callback(self, value):
        """
        Function called when setting the value of the setting via the decorator in inject.py
        Can be overridden if value transformation is needed prior to calling hooks
        """
        logger.info(f'{self.__class__.__name__} "{self.name}" for "{self.parent.__class__.__name__}" set to "{value}"')
        self.value = value

    @property
    def cli_arg(self) -> str:
        """
        Name of cli argument
        Defaults to --<hook name>-<setting name> (lowercased)
        Underscores in the setting name are replaced with hyphens
        """
        return f"--{self.parent.name}-{self.name.replace('_','-')}".lower()

    @property
    def env_var(self) -> str:
        """
        Name of environment variable
        Defaults to LIBMM_<ext name>_<setting name> (uppercased)
        Hyphens in the setting name are replaced with underscores
        """
        return f"LIBMM_{self.parent.name}_{self.name.replace('-','_')}".upper()


class NoCliHookSetting(UserHookSetting):
    """Standard extension setting but does not expose a CLI argument, only environment variable"""

    @property
    def cli_arg(self):
        return None


class NoEnvHookSetting(UserHookSetting):
    """Standard extension setting but does not expose an environment variable, only a CLI arg"""

    @property
    def env_var(self):
        return None


UserHookSettingT = TypeVar("UserHookSettingT", bound=UserHookSetting)


@dataclass
class Extension:
    name: str
    hook: UserHookT


def load_hooks_from_disk(extensions_directory: StrOrPath = global_settings.extensions_directory) -> List[Extension]:
    """
    Loads all first party extensions and (optionally) additional user-supplied extensions
    """
    all_paths = []
    # load first-party extensions stored in libmm/extensions
    with resource_path("libmm", "extensions") as p:
        all_paths.extend([z for z in p.rglob("*.py")])
    # load user supplied extensions, if any
    if extensions_directory is not None and extensions_directory != "":
        extensions_directory = resolve_str_or_path(extensions_directory)
        all_paths.extend([z for z in extensions_directory.rglob("*.py")])
    # short circuit if no extensions
    if len(all_paths) == 0:
        return []

    extensions = []
    for path in all_paths:
        # https://docs.python.org/3/library/importlib.html#importing-a-source-file-directly
        file_name = path.stem.lower()
        spec = importlib.util.spec_from_file_location(file_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if module.__name__ != "__init__":
            hook = getattr(module, "hook")
            extension = Extension(name=file_name, hook=hook)
            extensions.append(extension)
            logger.info(f'Loaded extension "{path.as_posix()}"')

        """
        # old method finds the hook class then inits it; new method just expects an init'd instance called "hook"
        for item in dir(module):
            item = getattr(module, item)
            if item != AbstractUserHook and inspect.isclass(item) and issubclass(item, AbstractUserHook):
                extension = Extension(name=file_name, hook=item())
                extensions.append(extension)
                logger.info(f'Loaded extension "{path.as_posix()}"')
        """

    return extensions


class ExtensionsManager:
    """
    Manages the loaded Extension classes and passes emitted events from the libraries to the extensions
    """

    def __init__(self):
        self.enabled = not global_settings.disable_extensions
        self.__extensions = []

        if self.enabled:
            hooks = load_hooks_from_disk()
            self.__extensions.extend(hooks)
            self.process_env_vars()
            self.emit_event(event=EventPairs.Init)

    def process_env_vars(self):
        """
        For each extension setting, if it has an environment variable
        poll the system environment variables for the value
        then set the value on the setting using its callback

        Note: This is not necessarily a duplicate of the Click environment variable resolution
        found in inject.py. That resolution will *only* in a CLI context since
        it is built on top of Click's CLI options. It also means the setting value will not
        be populated until after the CLI options are processed. This method performs
        value resolution during the init of the extension manager at a minimum, meaning
        the values will be resolved before any events are emitted.
        Developers should use environment variables if they require values be resolved
        immediately rather than waiting on CLI option processing.
        """
        for extension in self.__extensions:
            for setting in extension.hook.settings:  # type: UserHookSetting
                if ev := setting.env_var:
                    # its also possible to construct a dynamic Pydantic model
                    # using create_model that pulls from env vars similar to the global_settings
                    # but it would involve a lot of dynamicism in the extensions
                    # for it to be a useful method
                    #
                    # example:
                    #   >>> create_model("mymodel", attribute=(str, Field(env="ZZZ")), __base__=BaseSettings)
                    # (setting the base is required as BaseModel, the default base, doesnt
                    # resovle env vars)
                    if value := os.getenv(ev, None):
                        setting.value_callback(value)

    @property
    def extensions(self) -> List[Extension]:
        return self.__extensions

    def register_extension(self):
        return NotImplementedError

    def emit_event(self, event: EventPair, *args, **kwargs):
        """
        All extensions are passed all events without filtering
        Args/kwargs are passed into the context object of the event
        TODO: in the future, possibly allow extension to register only for specific events
        """
        if self.enabled:
            for extension in self.extensions:
                extension.hook.hook(event.event_type, event.context(*args, **kwargs))

    def match_setting_by_cli_arg(self, arg):
        for extension in self.extensions:
            for setting in extension.hook.settings:  # type: UserHookSetting
                if setting.cli_arg == arg:
                    return setting


def create_simple_extension_table(extension: UserHookT, name: str, fields: dict):
    """
    Generates a SQLModel table for an extension then adds it to the database.

    :param fields : Dictionary of column names -> column SQLAlchemy types for the table
    """
    from .sql import SQLModel, Field, Column

    """
    fields = dict()
    for setting in extension.settings:  # type: UserHookSetting
        fields[setting.name] = Field(sa_column=Column(String))
    """

    table_name = f"{extension.name.capitalize()}{name.capitalize()}"
    table = type(table_name, (SQLModel), {k: Field(sa_column=Column(v)) for k, v in fields.items()})
    SQLModel.metadata.create_all(bind=SQLModel.metadata.bind.engine, tables=[table])
    return table


extensions_manager = ExtensionsManager()
atexit.register(extensions_manager.emit_event, event=EventPairs.Exit)

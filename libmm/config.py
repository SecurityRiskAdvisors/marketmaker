from pydantic import BaseSettings, Field
from dataclasses import dataclass, field

from .type import Optional


"""
@dataclass
class Constants:
    def __post_init__(self):
        self.foo = "bar"


constants = Constants()
"""


class GlobalSettings(BaseSettings):
    # this does not appear to work with Field(env=...)
    #   e.g. env_prefix="FOO_" and env="BAR" looks for "BAR" not "FOO_BAR"
    # class Config:
    #     env_prefix = "LIBMM_"

    # general settings
    log_file_path: str = Field(default=".mm.log", env="LIBMM_LOGFILE_PATH")
    run_checks: bool = Field(default=True, env="LIBMM_RUN_CHECKS")
    add_d3fend: bool = Field(default=False, env="LIBMM_ADD_D3FEND")
    add_groups: bool = Field(default=False, env="LIBMM_ADD_GROUPS")
    disable_extensions: bool = Field(default=False, env="LIBMM_DISABLE_EXTENSIONS")
    extensions_directory: Optional[str] = Field(env="LIBMM_EXTENSIONS_DIRECTORY")
    db_file_path: str = Field(default="", env="LIBMM_DB_FILEPATH")
    db_text_delimiter: str = Field(default="||", env="LIBMM_DB_DELIMETER")
    db_file_autodelete: bool = Field(default=True, env="LIBMM_DB_AUTODELETE")
    experimental_features: bool = Field(default=False, env="LIBMM_EXPERIMENTAL_FEATURES")


global_settings = GlobalSettings()

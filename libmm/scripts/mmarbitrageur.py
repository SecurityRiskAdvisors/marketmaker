import nbformat
import click
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Union, List
import shlex
import textwrap
import json

from libmm.config import global_settings
from libmm.log import logger
from libmm.sql import LinkedData, session, Blueprint, init_db
from libmm.type import StrOrPath
from libmm.utils import resolve_str_or_path, load_yaml_from_file
from libmm.extension import extensions_manager, EventPairs
from libmm.scripts.shared import SharedOptions


"""
This extension will generate a Jupyter notebook can be imported into Mythic for use in
automating Variant execution.
It is currently designed to support the Apollo agent.
Where possible, it will integrate with the Guidance extension to add operator guidance to the
generated Jupyter notebook
"""

# https://nbformat.readthedocs.io/en/latest/api.html#module-nbformat.v4

MARKDOWN_NEWLINE = "\n\n"


def MARKDOWN_BOLDED(s):
    return f"**{s}**"


@dataclass
class AutomationConfigurationOptions:
    """
    Additional configurations for execution:

    - check_admin -> prevents execution if callback is not running as admin
    - file_upload -> creates a file upload widget then registers the file to the callback
    - dropper_upload -> creates a file upload widget then drops the file onto disk via the callback
    - user_inputs -> creates one or more user text inputs that can be accessed in command templates via the user_input macro
    """

    check_admin: bool = False
    file_upload: bool = False
    dropper_upload: bool = False
    user_inputs: dict = field(default_factory=dict)


CommandList = List[str | dict]


@dataclass
class AutomationConfigurationCli:
    #   good -> run_basic_task("execute_coff",{"coff_name": "env.x64.o", "function_name":"go", "timeout":"30", "arguments": []})
    #   bad -> run_basic_task("execute_coff", "-Coff env.x64.o -Function go -Timeout 30 -Arguments []") (or similar variations)
    # the dict keys are based on the agent_functions in the agent source code
    #   ex: apollo -> https://github.com/MythicAgents/Apollo/blob/master/Payload_Type/apollo/apollo/mythic/agent_functions
    #   use the CommandParameters in the TaskArguments
    #
    # using string inputs is fine for simple tasks like "shell whoami"
    run: CommandList
    setup: Optional[CommandList] = None
    cleanup: Optional[CommandList] = None


@dataclass
class AutomationConfiguration:
    cli: AutomationConfigurationCli
    options: Optional[AutomationConfigurationOptions] = field(default_factory=AutomationConfigurationOptions)

    @classmethod
    def from_yaml(cls, yaml: dict):
        # manually overriding these as them are commentedmaps from ruamel, not normal dicts
        if "cli" in yaml:
            yaml["cli"] = AutomationConfigurationCli(**yaml["cli"])
        if "options" in yaml:
            yaml["options"] = AutomationConfigurationOptions(**yaml["options"])
        return cls(**yaml)

    @classmethod
    def from_file(cls, path: StrOrPath):
        return cls.from_yaml(load_yaml_from_file(path))


class MdHeader(Enum):
    H1 = "#"
    H2 = "##"
    H3 = "###"
    H4 = "####"
    H5 = "#####"


class NbHelper:
    # TODO: need to handle auto init cells
    def __init__(self):
        self._nb = nbformat.v4.new_notebook()

        self._has_login = False
        self._has_callback = False

    def _append_cell(self, cell):
        self._nb["cells"].append(cell)

    def append_prereq_cell(self):
        codeblock = """
        !pip install nest-asyncio ipywidgets Jinja2
        """
        codeblock = textwrap.dedent(codeblock).strip()
        cell = nbformat.v4.new_code_cell(codeblock)
        self._append_cell(cell)

    def append_config_cell(self):
        codeblock = """
        from shared import *
        from mythic import mythic
        from IPython.display import display
        import nest_asyncio 
        nest_asyncio.apply()
        generate_login_widgets()
        """
        codeblock = textwrap.dedent(codeblock).strip()
        cell = nbformat.v4.new_code_cell(codeblock)
        # cell["metadata"]["init_cell"] = True
        self._append_cell(cell)

    def append_callback_widget(self):
        if self._has_callback:
            return

        cell = """generate_callback_selector()"""
        self._append_cell(nbformat.v4.new_code_cell(cell))

    def append_upload_widget(self, variant_id: str):
        cell = nbformat.v4.new_code_cell(f"""display(*generate_file_widget("{variant_id}"))""")
        # cell["metadata"]["init_cell"] = True
        self._append_cell(cell)

    def append_dropper_widget(self, variant_id: str):
        cell = nbformat.v4.new_code_cell(f"""display(*generate_file_widget("{variant_id}", dropper=True))""")
        # cell["metadata"]["init_cell"] = True
        self._append_cell(cell)

    def append_task_cell(self, cli: CommandList, variant_id: str, check_admin: bool = False, attire: bool = False):
        cell = ""
        for i, command in enumerate(cli):
            if isinstance(command, str):
                cli = shlex.split(cli)
                executor = cli[0]
                args = " ".join(cli[1:])
                sub_cell = f"""run_basic_task("{executor}","{args}", variant_id="{variant_id}", check_admin={check_admin}, attire={attire})"""
            elif isinstance(command, dict):
                k, v = list(command.items())[0]  # should only be 1 list item here
                sub_cell = f"""run_basic_task("{k}", {json.dumps(v)}, variant_id="{variant_id}", check_admin={check_admin}, attire={attire})"""
            else:
                raise Exception("Unknown CLI type")
            cell += sub_cell
            if i + 1 != len(cli):  # last item
                cell += "\n"
        self._append_cell(nbformat.v4.new_code_cell(cell))

    def append_md(self, text: str, header: MdHeader = None):
        if header:
            text = header.value + " " + text
        cell = nbformat.v4.new_markdown_cell(text)
        cell["metadata"]["editable"] = False
        self._append_cell(cell)

    def append_config_section(self):
        # TODO: hide source for these and others
        self.append_md(text="Configuration", header=MdHeader.H1)
        self.append_md(text="Step 0: Prerequisites", header=MdHeader.H3)
        self.append_md(text="This is only required once per server")
        self.append_prereq_cell()
        self.append_md(MARKDOWN_BOLDED("Then restart 'mythic_jupyter' container"))
        self.append_md(text="Step 1: Login", header=MdHeader.H3)
        self.append_config_cell()
        self.append_md(text="Step 2: Select Mythic callback", header=MdHeader.H3)
        self.append_callback_widget()

    def append_input_widget(self, inputs: List[tuple], variant_id: str):
        cell = ""
        for i, input_tuple in enumerate(inputs):
            sub_cell = f"""display(generate_input_widget({input_tuple[0]}, "{input_tuple[1]}", "{variant_id}"))"""

            cell += sub_cell
            if i + 1 != len(inputs):  # last item
                cell += "\n"

        cell = nbformat.v4.new_code_cell(cell)
        # cell["metadata"]["init_cell"] = True
        self._append_cell(cell)

    def save(self, path: StrOrPath):
        path = resolve_str_or_path(path)
        with path.open("w") as f:
            nbformat.write(self._nb, f)


@click.group()
def main():
    logger.info(f"Global settings resolved to: {global_settings.json()}")
    pass


@click.command(name="apollo")
@SharedOptions.techniques
@SharedOptions.blueprint()
@SharedOptions.outfile("j", "notebook", helptxt="Jupyter Notebook output file path", required=True)
@SharedOptions.infile("m", "mapping", helptxt="Input mapping file", required=True)
@click.option(
    "-g",
    "--include-opguidance",
    "opguidance",
    type=bool,
    help="include linked Operator Guidance from Guidance extension",
    default=False,
    is_flag=True,
)
def apollo(techniques, blueprint, notebook, mapping, opguidance: bool):
    init_db(techniques)

    blueprint = Blueprint.from_file(blueprint)
    jupyternb = NbHelper()
    # mapping of <variant id> to <AutomationConfiguration>
    mapping = load_yaml_from_file(mapping)

    extensions_manager.emit_event(event=EventPairs.LinkTableReady)

    jupyternb.append_config_section()

    jupyternb.append_md(text="---")
    jupyternb.append_md(text="Execution", header=MdHeader.H1)
    jupyternb.append_md(text="---")

    preamble = f"# {blueprint.name}{MARKDOWN_NEWLINE}{blueprint.description}"
    if opguidance:
        for row in (
            session.query(LinkedData)
            .filter(LinkedData.blueprint_id == blueprint.id, LinkedData.origin == "guidance")
            .all()
        ):
            preamble += MARKDOWN_NEWLINE
            preamble += row.data
    jupyternb.append_md(text=preamble)

    for campaign in blueprint.child_campaigns:
        jupyternb.append_md(text=campaign.name, header=MdHeader.H2)

        for variant in campaign.variants:
            jupyternb.append_md(text=variant.display_name, header=MdHeader.H3)
            jupyternb.append_md(text=variant.description)

            if opguidance:
                for row in (
                    session.query(LinkedData)
                    .filter(LinkedData.variant_id == variant.id, LinkedData.origin == "guidance")
                    .all()
                ):
                    jupyternb.append_md(
                        text=f"{MARKDOWN_BOLDED('Guidance notebook')}:{MARKDOWN_NEWLINE}````\n{row.data}\n````"
                    )

            if variant.guidance:
                original_guidance = "\n".join(variant.guidance)
                # TODO: newlines in block arent rendering properly
                jupyternb.append_md(
                    text=f"{MARKDOWN_BOLDED('Original guidance')}:{MARKDOWN_NEWLINE}```\n{original_guidance}\n```"
                )

            if config := mapping.get(variant.id, None):
                config = AutomationConfiguration.from_yaml(config)

                if inputs := config.options.user_inputs:
                    jupyternb.append_md(text="Inputs required", header=MdHeader.H4)
                    jupyternb.append_input_widget(inputs=list(inputs.items()), variant_id=variant.id)

                if config.options.file_upload:
                    jupyternb.append_md(text="Callback payload required", header=MdHeader.H4)
                    jupyternb.append_upload_widget(variant.id)
                if config.options.dropper_upload:
                    jupyternb.append_md(text="File payload required", header=MdHeader.H4)
                    jupyternb.append_dropper_widget(variant.id)

                if config.cli.setup:
                    jupyternb.append_md(text="Setup", header=MdHeader.H4)
                    jupyternb.append_task_cell(
                        config.cli.setup, variant_id=variant.id, check_admin=config.options.check_admin
                    )
                if config.cli.run:
                    jupyternb.append_md(text="Run", header=MdHeader.H4)
                    jupyternb.append_task_cell(
                        config.cli.run, variant_id=variant.id, check_admin=config.options.check_admin, attire=True
                    )
                if config.cli.cleanup:
                    jupyternb.append_md(text="Cleanup", header=MdHeader.H4)
                    jupyternb.append_task_cell(
                        config.cli.cleanup, variant_id=variant.id, check_admin=config.options.check_admin
                    )

    jupyternb.save(notebook)


main.add_command(apollo)


if __name__ == "__main__":
    main()

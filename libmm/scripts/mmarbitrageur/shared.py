from mythic import mythic, mythic_classes
from ipywidgets import widgets
from IPython.display import display, FileLink
import asyncio
import ast
from enum import Enum, auto
from typing import List
import time
import base64
import json
from copy import copy
import jinja2
import datetime
import uuid
import pathlib

"""
Shared Python functions for use by Arbitrageur-generated notebooks
"""

DEFAULT_TIMEOUT = 30
MythicClient = mythic_classes.Mythic


# TODO: intial design was to store the widget ref then grab the value from the widget as needed (like with the username/pass)
#       but subsequent additions just stored the values directly on the state
#       object using the widget traitlet events
#       not sure which is preferable but should standardize on one or the other
class UserIoWidget(Enum):
    Username = auto()
    Password = auto()
    Callback = auto()
    Output = auto()


class SharedState:
    def __init__(self):
        self._widget_store: dict = {}
        self.mythic_client: MythicClient = None
        # TODO: inmem sqlite or mm sql table
        self.process_ids: dict = {}
        self.uploaded_files: dict = {}  # tracks uploads 1:1, not a running list
        self.user_inputs: dict = {}  # tracks required inputs by variant id
        self.callback_details: dict = {}
        self.attire_procedures: dict = {}
        # self.attire_step_ct: int = 1

    def set_widget(self, widget: UserIoWidget, instance):
        self._widget_store[widget] = instance

    def get_widget(self, widget: UserIoWidget):
        return self._widget_store.get(widget, None)

    def get_widget_value(self, widget: UserIoWidget):
        if w := self.get_widget(widget):
            return w.value
        else:
            return

    def check_mythic_auth(self):
        # need to do it this way since asyncio.run() wont work inside a notebook
        # as ipython has its own event loop
        self.mythic_client: MythicClient = asyncio.run(
            mythic.login(
                username=self.get_widget_value(UserIoWidget.Username),
                password=self.get_widget_value(UserIoWidget.Password),
                server_ip="mythic_nginx",
                server_port=7443,
                timeout=DEFAULT_TIMEOUT,
                ssl=True,
            )
        )
        self.mythic_client.global_timeout = DEFAULT_TIMEOUT

    def login_form_callback(self, widget):
        output_widget = self.get_widget(UserIoWidget.Output)
        output_widget.clear_output()
        try:
            self.check_mythic_auth()
        except Exception as e:
            output_widget.append_display_data(e)

    @property
    def current_callback_id(self):
        # the callback tuples only store the id
        # has issues with stored the entire callback object in the dropdown
        return self.get_widget_value(UserIoWidget.Callback)

    @property
    def current_callback_is_admin(self):
        callbacks = asyncio.run(mythic.get_all_callbacks(mythic=self.mythic_client))
        callback = list(filter(lambda x: x["display_id"] == self.current_callback_id, callbacks))
        if len(callback) == 1:
            # admin callbacks have a level of 3
            return callback[0].get("integrity_level", 2) > 2
        else:
            raise Exception("Error filtering callbacks or no callbacks to filter")

    def get_process_id_by_name(self, name: str):
        if proc_id := self.process_ids[self.current_callback_id].get(name, None):
            return proc_id
        else:
            raise Exception(f"No process id for process: '{name}'")


state = SharedState()


@jinja2.pass_context
def uploaded_file(ctx, *args, **kwargs):
    # {{ uploaded_file }} -> 'procdump.exe'
    if variant_id := ctx.environment.active_variant_id:
        if file_name := state.uploaded_files.get(variant_id, None):
            return file_name
        else:
            raise Exception("No file uploaded")
    else:
        raise Exception("No variant set")


@jinja2.pass_context
def pidof(ctx, value, *args, **kwargs):
    # {{ pidof("lsass.exe") }} -> '600'
    return state.get_process_id_by_name(value)


@jinja2.pass_context
def user_input(ctx, value: int, *args, **kwargs):
    # {{ user_input(1) }} -> 'abcdef'
    # requires the user_inputs option is configured in the mapping
    if variant_id := ctx.environment.active_variant_id:
        if input_dict := state.user_inputs.get(variant_id, None):
            value = int(value)
            if value in input_dict:
                return input_dict.get(value)
    raise Exception("Cannot get user input")


jinja_env = jinja2.Environment()
jinja_env.globals.update(uploaded_file=uploaded_file)
jinja_env.globals.update(pidof=pidof)
jinja_env.globals.update(user_input=user_input)
jinja_env.active_variant_id = None


def generate_login_widgets():
    # TODO: use widget observe events
    user_form_field = widgets.Text(value="", description="User", placeholder="Mythic user", disabled=False)
    state.set_widget(UserIoWidget.Username, user_form_field)

    password_form_field = widgets.Text(value="", description="Password", placeholder="Mythic password", disabled=False)
    state.set_widget(UserIoWidget.Password, password_form_field)

    output = widgets.Output()
    state.set_widget(UserIoWidget.Output, output)

    submit_button = widgets.Button(description="Submit", disabled=False)
    submit_button.on_click(callback=state.login_form_callback)

    display(user_form_field, password_form_field, submit_button, output)


def generate_callback_selector():
    # active seems to mean hidden/not hidden not whether or not its received a checkin
    callbacks = asyncio.run(mythic.get_all_active_callbacks(mythic=state.mythic_client))
    callback_list = []
    for callback in callbacks:
        cb_id = callback.get("display_id")  # issue task uses the display_id, not the id
        cb_host = callback.get("host")
        # the ip "list" is actually a string representation of a list so eval it to make it a list
        cb_ip = ast.literal_eval(callback.get("ip"))[0]
        display_name = f"#{cb_id} {cb_host} ({cb_ip})"
        callback_list.append((display_name, cb_id))
        state.callback_details[cb_id] = copy(callback)

    widget = widgets.Dropdown(options=callback_list, value=None, description="Callback", disabled=False)

    widget.observe(get_process_ids_for_callback, names="value", type="change")

    state.set_widget(UserIoWidget.Callback, widget)
    return widget


def format_task_output(output: bytes) -> str:
    # return output.decode("unicode-escape").strip()
    return output.decode().strip()


def run_task_internal(executor, args: str | dict):
    mythic_task = asyncio.run(
        mythic.issue_task(
            mythic=state.mythic_client,
            command_name=executor,
            parameters=args,
            callback_display_id=state.current_callback_id,
            wait_for_complete=True,
        )
    )

    try:
        task_id = mythic_task.get("display_id")
    except KeyError as e:
        # TODO
        raise e
    else:
        task_output = asyncio.run(mythic.waitfor_for_task_output(mythic=state.mythic_client, task_display_id=task_id))
        return task_output


def run_basic_task(executor, args: str | dict, variant_id: str, check_admin: bool = False, attire: bool = False):
    if check_admin:
        if not state.current_callback_is_admin:
            raise Exception("Task requires admin callback")

    jinja_env.active_variant_id = variant_id
    arg_str = ""

    if isinstance(args, str):
        args = jinja_env.from_string(args).render()
        arg_str = args
    # TODO: handle arbitrary depth?
    elif isinstance(args, dict):
        new_args = {}
        for k, v in args.items():
            # have to handle COFF args differently due to the complex structure of Mythic's TypedArray
            if k == "coff_arguments":
                new_coff_args = []
                # COFF args are supplied as a list of 2-item lists ([type, value])
                for coff_arg in v:
                    if isinstance(coff_arg[1], str):
                        new_coff_arg = [coff_arg[0], jinja_env.from_string(coff_arg[1]).render()]
                        new_coff_args.append(new_coff_arg)
                    else:
                        new_coff_args.append(coff_arg)
                new_args[k] = new_coff_args
            elif isinstance(v, str):
                new_args[k] = jinja_env.from_string(v).render()
            else:
                new_args[k] = v
        args = new_args
        arg_str = json.dumps(args)

    time_start = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")
    task_output = run_task_internal(executor=executor, args=args)
    time_end = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.000Z")

    output = format_task_output(task_output)
    print(output)


    # TODO: most of this attire code is fine, but the ids are not correct
    #       waiting for planned changes to attire data import in vectr
    #       before fixing. if you need attire support working, you will
    #       need to get the user-mode test case IDs from the assessment 
    #       so the logs import properly
    if attire:
        step = {
            "command": f"{executor}> {arg_str}",
            # "order": 1,
            "time-start": time_start,
            "time-stop": time_end,
            "output": [{"content": output, "level": "STDOUT", "type": "console"}],
        }
        if variant_id not in state.attire_procedures:
            attire_procedure = {"procedure-id": {"type": "guid", "id": variant_id}, "steps": []}
            # callback_host = state.callback_details.get(state.current_callback_id).get("host")
            # storing these under the variant to prevent issues where you run
            # a command, then change the callback, then run it again as this leads
            # to duplicate logs for the same test case
            state.attire_procedures[variant_id] = (state.current_callback_id, attire_procedure)

        # TODO: handle repeat commands on the same host
        #       no way to determine multiple task cells vs re-running the same cell
        steps = state.attire_procedures[variant_id][1]["steps"]
        step_ct = len(steps) + 1
        step["order"] = step_ct
        steps.append(step)


async def wrap_mythic_async_generator(fn, *fn_args, **fn_kwargs):
    async for item in getattr(mythic, fn)(*fn_args, **fn_kwargs):
        yield item


# never use async python unless you want to catch a case of async =(
def sync_iter_mythic_async_generator(fn, *fn_args, **fn_kwargs):
    # based on https://stackoverflow.com/a/75914396
    generator = wrap_mythic_async_generator(fn, *fn_args, **fn_kwargs)
    event_loop = asyncio.get_event_loop()
    items = []
    try:
        while True:
            items.extend(event_loop.run_until_complete(generator.__anext__()))
    except StopAsyncIteration as e:
        pass
    except Exception as e:
        state.get_widget(UserIoWidget.Output).append_display_data(e)

    return items


def get_uploaded_files_by_name(name: str, latest: bool = True) -> dict | List[dict]:
    files = sync_iter_mythic_async_generator("get_all_uploaded_files", mythic=state.mythic_client)
    filtered_files = list(filter(lambda x: x.get("filename_utf8", "") == name, files))
    if latest:
        sorted_files = sorted(
            filtered_files,
            key=lambda x: time.mktime(time.strptime(x["timestamp"], "%Y-%m-%dT%H:%M:%S.%f")),
            reverse=True,
        )
        return sorted_files[0]
    return filtered_files


def generate_file_widget(variant_id: str, dropper: bool = False):
    widget = widgets.FileUpload(multiple=False)
    label = widgets.Label("")

    # need to nest here so the fn has access to the label
    def register_file_to_callback(change: dict):
        label.value = "Uploading..."

        new_file = change.get("new")[0]
        file_name = new_file.name
        state.uploaded_files[variant_id] = file_name

        file_id = asyncio.run(
            mythic.register_file(
                mythic=state.mythic_client, filename=new_file.name, contents=new_file.content.tobytes()
            )
        )

        # dropper mode = upload file to disk
        # default = register file to callback
        # if uploading to disk, the uploaded file name matches the original file name when not specified
        command_name = "upload" if dropper else "register_file"
        asyncio.run(
            mythic.issue_task(
                mythic=state.mythic_client,
                command_name=command_name,
                # workaround for https://github.com/MythicAgents/Apollo/issues/149 need to provide remote_path
                parameters={"file": file_id, "remote_path": file_name},
                callback_display_id=state.current_callback_id,
                wait_for_complete=True,
            )
        )
        # https://stackoverflow.com/a/74332263
        label.value = "Upload complete"

    widget.observe(register_file_to_callback, names="value", type="change")
    # display(*generate_file_widget()) -> need to unpack first
    return widget, label


def get_process_ids_for_callback(*args, **kwargs):  # swallow args from observe
    if state.current_callback_id:
        ps = run_task_internal(executor="ps", args="")
        ps_parts = ps.decode().split("][")

        ps_dict = {}
        # TODO: does not handle duplicate process names properly -> fix

        # TODO: come back to this. not sure why, but the output has multiple json outputs cat'd together
        for part in ps_parts:  # type: str
            if len(part) > 1:
                if not part.endswith("]"):
                    part = part + "]"
                if not part.startswith("["):
                    part = "[" + part

                ps_list = json.loads(part)
                # pull proc name from bin_path to retain extension
                ps_sub_dict = {proc.get("bin_path").split("\\")[-1].lower(): proc.get("process_id") for proc in ps_list}
                ps_dict = {**ps_dict, **ps_sub_dict}

        state.process_ids[state.current_callback_id] = copy(ps_dict)


def generate_input_widget(input_id: int, label: str, variant_id: str):
    widget = widgets.Text(
        description=label, disabled=False, style={"description_width": "initial"}, layout=widgets.Layout(width="85%")
    )

    def update_inputs_dict_callback(change: dict):
        new_value = change.get("new")
        state.user_inputs.setdefault(variant_id, {})[input_id] = new_value

    widget.observe(update_inputs_dict_callback, names="value", type="change")

    return widget


def export_attire_logs() -> dict:
    data_by_host = {}

    for variant_id, data in state.attire_procedures.items():
        callback_id, attire_procedure = data
        callback_details = state.callback_details.get(callback_id)
        callback_host = callback_details.get("host")

        user_str = ""
        if user_domain := callback_details.get("domain", None):
            user_str += user_domain
            user_str += "\\"
        user_str += callback_details.get("user")

        if callback_host not in data_by_host:
            attire_dict = {
                "execution-data": {
                    "execution-id": str(uuid.uuid4()),
                    "execution-source": "Market Maker Arbitrageur",
                    "target": {
                        # vectr only displays the ip in the UI
                        "ip": f"{callback_host} ({callback_details.get('ip')})",
                        "host": callback_host,
                        "user": user_str,
                    },
                },
                "procedures": [],
                "attire-version": "1.1",
            }
            data_by_host[callback_host] = attire_dict

        data_by_host[callback_host]["procedures"].append(attire_procedure)

    return data_by_host


def save_attire_logs():
    # TODO: put all files into zip?
    log_dict = export_attire_logs()
    links = []
    for host, logs in log_dict.items():
        fname = f"{host}_attire.json".replace(" ", "")
        pathlib.Path(fname).write_text(json.dumps(logs, indent=4))
        link = FileLink(fname, result_html_prefix="Log saved to: ")
        links.append(link)

    return links

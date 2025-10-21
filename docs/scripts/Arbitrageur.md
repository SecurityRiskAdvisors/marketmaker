# MM Arbitrageur

The `mm-arbitrageur` tool provides the following subcommands:

- `apollo` used for generating Jupyter notebooks that automate execution using Mythic's Apollo agent via the Mythic JupyterLab server

## Use

```
Usage: mm-arbitrageur apollo [OPTIONS]

Options:
  -t, --technique-paths TEXT  One or more paths to technique directories.
                              Concatenate paths with a ':'. For example:
                              /foo:/bar. Defaults to 'techniques/'  [required]
  -b, --blueprint FILE        path to blueprint   [required]
  -j, --notebook FILE         Jupyter Notebook output file path  [required]
  -m, --mapping FILE          Input mapping file  [required]
  -g, --include-opguidance    include linked Operator Guidance from Guidance
                              extension
  --help                      Show this message and exit.
```

`--include-opguidance` can be supplied to include operator guidance from the [Guidance](../extensions/Guidance.md) extension. Mapped guidance will be included within a Markdown codeblock. Be sure to provide the Guidance extension options via environment variables.


## Mapping

The mapping document is a YAML file that maps from Variant IDs to the execution details. The full schema is:

```
<variant ID>:
  cli:
    setup: Map[]
    run: Map[]!
    cleanup: Map[]
  options:
    file_upload: Bool
    dropper_upload: Bool
    check_admin: Bool
    user_inputs: Map
```

The `cli` section is where the execution steps are covered. The `options` section is where addition behaviors are configured.

The `cli` section has three subsections, `setup`, `run`, and `cleanup`. These sections are meant to align to the stages of executing a test case: 1) run and prerequisite setup commands like making directories, 2) run the main steps, then 3) cleanup any created artifacts like Registry keys. The mappings list for these sections all follow the same structure and only the `run` section is required. The structure is a list of mappings, where each map is aligns with the Mythic Apollo module to run and its arguments. For example, if you want to run a .NET executable via `execute_assembly`, it would look like:

```yaml
run: 
- execute_assembly:
    assembly_name: 'mydotnetfile.exe'
    assembly_arguments: 'foo'
```

The key in the mapping is the Apollo command name and the value is a mapping of the argument names to the argument values. Note: The arguments in this mapping are based on the Apollo command parameter names as used by the API, not the console. For example, with `execute_assembly` the assembly name is provided via the `-Assembly` argument when using the Mythic console, but should be specified as via `assembly_name` in the mapping. Refer to the `CommandParameter`s (`name` property) in the corresponding Apollo command source code for paraemeter details (https://github.com/MythicAgents/Apollo/blob/master/Payload_Type/apollo/apollo/mythic/agent_functions).

The `options` section allows for additional controls in the UI to help with more complex execution scenarios and dependencies. These are all optional. Currently, there are four options available for this section:

- `file_upload`: Adds a file upload button widget that will upload the file to the Mythic server then register it to the current callback
- `dropper_upload`: Same as `file_upload` but the file will be dropped to disk via the current callback rather than registered
- `check_admin`: Checks that the current callback has administrator privileges before execution then fails if not running as admin.
- `user_inputs`: Adds one or more text field widgets for users to supply inputs to the command cells. Required for the `user_input` template macro (see below)

## Command Template Macros

Values in command arguments can make use of several convenience macros for accessing additional data. The following macros are available:

- `uploaded_file()`: Get the file name (name, not path) of the file uploaded through a generated file/dropper upload widget
- `pidof(process_name)`: Get the proces ID corresponding to the supplied process name*
- `user_input(input_id)`: Get the user-supplied value for the specified input field

The `user_input` macro requires two components to function as expected. First, you must provide a `user_inputs` section in the mapping options. This is a mapping of an input ID number and an input label. Ex:

```yaml
options:
  user_inputs:
    1: "Your name"
    2: "Your favorite color"
```

The ID is an arbitrary integer. The label is an arbitrary string that will be displayed to the user. The macro should use the ID to retrieve the value supplied in that input's form field. For example, with the above, two widgets will be generated for the user. To access the value entered into the "Your name" input, use `user_input(1)`.

Command macros are Python Jinja templates and must be enclosed in double curly braces (e.g. `{{ macro() }}`).

*Note: When you select a Mythic callback from the callback selector, it will queue a `ps` command then cache the results. When using the `pidof` macro, the ID will be pulled from these cached results. If you know a process ID will change at some point before execution (or a new process will spawn, etc), you can run the `get_process_ids_for_callback()` function to manually trigger a new `ps` command and store its results.*

## Shared Functions

There are two components to Arbitrageur: 1) the Arbitrageur script and 2) a shared functions file. The Arbitrageur script simply generates the Jupyter notebook, which is then uploaded to Mythic's JupyterLab. The functions within that notebook originate in a shared functions file that must also be uploaded adjacent to the notebook. This shared functions file implements all logic for the notebook functions, like connecting to the Mythic API, creating widgets, storing callback data, etc. Data is persisted in a `state` object from this module (for example, the cached process data noted above).

## Requirements

The generated notebook requires a shared functions file be uploaded adjacent to it. 

You must also run the Step 0 instructions prior to execution. This will install the Python requirements. You must then restart the Jupyter Mythic container.

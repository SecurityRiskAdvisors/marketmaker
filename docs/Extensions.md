# Extensions - User

Extensions enable users to extend the functionality of `libmm`. Extensions follow a simple eventing system where certain actions within `libmm` will emit events and a corresponding context that can be consumed.

By default, extensions are loaded. To disable extensions, use `LIBMM_DISABLE_EXTENSIONS`.

## Extension Loading

Extension are always loaded from the `libmm/extensions` directory inside the module and can optionally also be loaded from a directory specified in `LIBMM_EXTENSIONS_DIRECTORY`.

# Extensions - Developer

Relevant extension code can be found in `libmm/extensions.py`.

At a minimum, extensions (referred to in the code as a "user hook") should be a valid Python file, contain a Python class that inherits `AbstractUserHook`, and implements the abstract functionality of `AbstractUserHook`. The extension should also have an instance of that class called `hook` within the code.

Example:

```python
from libmm.extension import AbstractUserHook
class MyExtension(AbstractUserHook):
    # ...
    pass
hook = MyExtension()
```

Warning: Extension exection is handled sychronously, meaning individual extensions can cause the primary application to hang.  

## AbstractUserHook

The `AbstractUserHook` abstract class exposes the methods used by `libmm` to call the extension code:

- `name` should return a string containing the name of the extension
- `settings` should return a list of `UserHookSetting`. These are used to retrieve user-supplied input
- `hook` is the function called when an event is emitted

## UserHookSetting

`UserHookSetting` provide a mechanism for users to supply inputs to an extension within the confines of `libmm` conventions.

`UserHookSetting` should implement a `value_callback` function that will be called when `libmm` sets the value of the setting.

Settings are injected into `libmm` CLI application via the `libmm.inject.opts_from_extensions()` decorator (for use with `Click`-based CLI application). Users can provide values either directly as CLI args or via environment variables. It is important to note that an extension will still load and run in all `libmm` applications (assuming it was not explicitly disabled) even if no CLI is present. In either case, the value is provided as a string. The names of the CLI args and environment variables are determined via the following rules:

- CLI: lowercase( "--" + \<extension name> "-" + \<setting name> )
- Env: uppercase( "LIBMM_" + \<extension name> "_" + \<setting name> )

These names can be overridden by implementing the `cli_arg` and `env_var` properties in the extension class. 

*Note: users are responsible for ensuring there is no overlap in CLI/env names, so it is best to properly document any changes to the above conventions.*

Keep in mind the order in which actions occur within `libmm` when requiring user inputs. For example, if the value of a user input is required prior to when a `CliStart` event would be called, you should instruct users to supply the value as an environment variable and possibly also disable the CLI argument for that setting (you can use `NoCliHookSetting` in place of the standard `UserHookSetting` to accomplish this). This will also be required for extensions that function outside of CLI contexts, such when using the LinkedData table (see below) or when registering a database ORM event.

## LinkedData Table

The LinkedData (`libmm.sql.LinkedData`) table is used to expose non-core `libmm` data (e.g. data from extensions) to other consumers via the core `libmm`. If you are writing a script that uses `libmm` and need to access data managed by an extension, the extension developer can expose that data without requiring you to have knowledge of the extension internals. As an example: the 1st-party [Guidance extension](extensions/Guidance.md) exposes all Variant-guidance pairs (per the provided mapping) via the LinkedData table so that other developers can access the operator guidance on a per-Variant basis.

The LinkedData table stores data that is tied to either a Blueprint or a Variant (only one per row). Extension developers must also supply the data in one of the expected data formats (see `libmm.sql.LinkedDataFormat`).

If your application expects to use the LinkedData table, it should emit the `LinkTableReady` as this event is not normally emitted by `libmm`. It should emit this after data is initally loaded into the database (e.g. `init_db(...)` -> `emit_event(event=LinkTableReady)`).

## Quick start

The following example shows how to create a minimal extension

**Step 1**: Create the skeleton

```python
from libmm.extension import AbstractUserHook

class MyExtension(AbstractUserHook):
    def __init__(self):
        pass
    
    @property
    def name(self):
        return "myextension"
        
    @property
    def settings(self):
        return []
        
    def hook(self, event_type, context):
        pass
        
hook = MyExtension()
```

This skeleton implements all abstract functionality as no-ops.

**Step 2**: Add settings

```python
from libmm.extension import AbstractUserHook, UserHookSetting

class MyExtension(AbstractUserHook):
    def __init__(self):
        self._settings = {
            "input": UserHookSetting(name="input", parent=self)
        }

    @property
    def settings(self):
        return list(self._settings.values())
```

The setting defined here will now show up in all CLI applications that implement argument injection. Users will supply the value as `--myextension-input` or via the environment variable `LIBMM_MYEXTENSION_INPUT`.

**Step 3**: Hook desired event types

```python
from libmm.extension import AbstractUserHook, EventTypes

class MyExtension(AbstractUserHook):
    def hook(self, event_type, context):
        if event_type == EventTypes.CliStart:
            print(f"{self._settings.get('input')}")
```

Since all emitted events are passed to all extensions, the extension must filter to only the events it is interested in. In this case, the extension will print the user-supplied input when the CLI application starts.

**Combined**

```python
from libmm.extension import AbstractUserHook, UserHookSetting, EventTypes

class MyExtension(AbstractUserHook):
    def __init__(self):
        self._settings = {
            "input": UserHookSetting(name="input", parent=self)
        }
    
    @property
    def name(self):
        return "myextension"

    @property
    def settings(self):
        return list(self._settings.values())
        
    def hook(self, event_type, context):
        if event_type == EventTypes.CliStart:
            print(f"{self._settings.get('input')}")

hook = MyExtension()
```


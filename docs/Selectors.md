# Selectors

Selectors are a standardized mechanism `libmm` provides for selecting Blueprints and Variants from a Library based on the characteristics of the Blueprint/Variant (rather than by ID). This is primarily intended to be used by extensions that require mappings between their extension-specific data and Library contents.

> Selectors are currently considered experimental functionality. You must enable the `libmm` experimental features setting to use them (see [EnvVars.md](EnvVars.md)).

## Format

Selectors use the following format:

```
selector(<OBJECT TYPE> <PROPERTY>[<OPERATOR><VALUE>])
```

- The object type is either `variant` or `blueprint`
- The property is the object's property
  - Variants allow: `id`, `tid`, `tactic`, and `name`
  - Blueprints allow: `id`, `name`, and `prefix`
- The operator is the comparison operator and is either `==` for direct comparison (case-sensitive comparison) or `~=` for approximate comparison (case-insensitive substring comparison). The value is the comparison value. These are required for the above listed properties but are optional for some special properties.

You can define one or more properties in a selector. The property can also be a special property, which means it provide filtering beyond a naive comparison. The following special properties are available:

- Variants:
  - `requires_ladmin`: checks if `local_admin` is in the Variant's prerequisites

## Example selectors

Match Variant by an ID

```
selector(variant id=='48008298-ad39-4663-8c53-0be12650c671')
```

Match all Variants with TID T1021.003 with a name containing "WMI"

```
selector(variant tid=='T1021.003' name~='wmi')
```

Match all Variants that require Local Admin with a name containing "Persist"

```
selector(variant requires_ladmin name~='persist')
```

Match all Blueprints with a Prefix containing "FSI"

```
selector(blueprint prefix~='fsi')
```

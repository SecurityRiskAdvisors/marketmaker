# Blueprints

Blueprints are documents that define the contents of an attack plan and are used an input for generating content. 

*Note: ! is used to denote a mandatory field*

## Schema

Blueprints use the following format:

```
name: String!
description: String!
sources: String[]
metadata: Map
campaigns: Map!
groups: Map
```

Only the `name`, `description`, and `campaigns` fields are required ("!").

The `name` is an arbtitrary name for the blueprint, but should generally be the name of whatever you plan to refer to the export as. For example, if you are creating your Q2 test plan, you could name the blueprint "Q2 Test Plan". The same applies to the `description`.

`sources` is a list of links that are relevant to the blueprint, such as those that were used as the basis for the plan development.

### Metadata

Metadata is arbitrary key-value pairs but requires the `id` key with a UUID value at a minimum.

If you are planning to use the exported manifest with VECTR, use the following metadata:

```
metadata:
  id: String!
  vectr:
    prefix: String!
    assessment: String!
```

Where `prefix` is the prefix test case templates will be given for the template management sections of VECTR and `assessment` is the Assessment Group template name the test cases will be grouped under.

### Campaign

Campaigns list the test cases to include in the bundle and follow the structure:

```
campaigns:
  Campaign Name:
    Technique ID: Variant
```

The campaign name can be an arbitrary value.

`Variant` can be one of the following two structures:

```
variant name: Int!
```

or 

```
variant name:
  version: Int!
  name: String
  guidance: String[]
  references: String[]
```

This second form can be used to override select fields of the Variant at the Blueprint level. For example, if you need to override the guidance for this export without modifying the underlying Variant file, you can provide it directly in the Blueprint.

An example using both:

```
campaigns:
  Command and Control:
    T1071.001:
      httpsc2: 1
    T1071.004:
      dnsc2:
        version: 1
        name: "Example name override"
```

In most cases, users should stick with the first form.

### Groups

Groups are used to add additional threat group metadata to exported test cases and follow the structure:

```
groups:
  Group name:
  - Technique ID
  - Technique ID
```

The group name is an arbitrary value.

For each instance of the technique ID in the campaigns section, the variant will have the group name added to its metadata.

An example:

```
campaigns:
  Command and Control:
    T1071.001:
      httpsc2: 1
groups:
  APTX:
  - T1071.001
```

Will modify the `httpsc2` variant in the export to have `APTX` in the `group` metadata:

```
name: HTTPS C2
metadata:
  groups:
  - APTX
```

*Note: this requires the `LIBMM_ADD_GROUPS` feature to be enabled. See [EnvVars.md](EnvVars.md) for details.*

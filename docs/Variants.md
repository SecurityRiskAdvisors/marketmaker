# Variants

Variants are the test case documents. There are two components to a variant: its path in a library and its file contents.

**Note: Generally, the original Variant file contents are left unchanged by `libmm`. The discussed transformations below are for the exported Variant, where exported refers to functions that reproduce the Variant contents in some way (e.g. in a Manifest).**

## In a library

In a test case library, variants should be organized by the variant name, with different versions of the same Variant being adjacent to one another. Variant versions should be relatively similar to one another. If versions differ significantly, they should be organized under a new variant name. For example, if you are creating different version of Windows service persistence, different command-line arguments for `sc.exe` creating a service could be organized under the same variant but creating a service with `reg.exe` would be a different variant.

## File Schema

Variants should use the following schema inside the file:

```
name: String!
description: String!
metadata: Map
platforms: String[]
prerequisites: String[]
guidance: String[]
block: String[]
detect: String[]
controls: String[]
```

The `name` is the display name for the test case. The same applies to the `description`.

`platforms` is a list platforms, such as operating systems and cloud providers. This field is only required if a test case is platform(s)-specific. These should be formatted as lowercase strings (e.g. "windows").

`prerequisites` is a list of permission requirements for executing the test case, such as local administrator or logon rights. These should be formatted as "_"-delimted lowercase strings (e.g. "local_admin").

`guidance` is a list of commands and/or steps. 

`block` and `detect` are both lists high-level block/detect descriptions. These values can also be partials identifiers (see [Partials.md](extensions/Partials.md)).

`controls` is a list a possible security controls that are relevant to the test case.

### Metadata

Variant metadata uses the following schema:

```
id: String!
isv: Integer!
tactic: String!
tid: String!
tools: String[]
references: String[]
mav: Integer
```

`id` is a UUID.

`isv` is the variant schema version. This should always be `1` as there is currently only one schema version, 1.

`tid` is the MITRE Technique ID and `tactic` is the MITRE Tactic ID.

`tools` is a list of tool names/links.

`references` is a list of links related to the test case, such as thhe threat intelligence reports the test case was based on.

`mav` is the MITRE ATT&CK major version (e.g. 13, 14)

### MITRE D3FEND

MITRE D3FEND integration is available for exported Variants. This is controlled via the environment variables `LIBMM_ADD_D3FEND`.

This variable enables the use of D3FEND and will attach D3FEND Offensive Artifacts as metadata to the exported Variants under the key `x_d3fend`. Artifacts are based on the D3FEND inferred mappings of ATT&ACK IDs -> offensive artifacts. For each of these artifacts, the corresponding D3FEND Countermeasures are mapped to the artifact. Countermeasures are based on the D3FEND inferred mappings of Offensive Artifacts -> Defensive Countermeasures.


# Guidance Extension

This extension generates Markdown documents for a Blueprint based on a provided mapping file (see below).

Operator guidance allows test case content developers to provide significantly more details than what can reasonably be included in the test case guidance section.

Guidance documents are stored in a directory as individual Markdown files then merged by this extension.

## Guidance document format

Guidance documents must use the following structure for their Markdown sections:

```
---
x_guidance_id: 00000000-0000-0000-0000-000000000000
gsv: 1
---

# {{ Title }}

{{ content }}

## [1] {{ Version 1 }}

{{ content }}

### Prerequisites

{{ content }}

### Guidance

{{ content }}

### Cleanup

{{ content }}

### Notes

{{ content }}

### References

{{ content }}
```

Breaking this down, the first section is Markdown front-matter that contains metadata about the document.

```
---
x_guidance_id: 00000000-0000-0000-0000-000000000000
gsv: 1
---
```

`x_guidance_id` is a UUID and is used to locate the particular document in the guidance library. `gsv` is the guidance document schema version. This should always be `1` as there is currently only one schema version, 1.

```
# {{ Title }}

{{ content }}

## [1] {{ Version 1 }}

{{ content }}
```

Guidance documents are structured as multiple sub-documents grouped together under one overarching document. The title (h1) and first content section describe the general overaching concept. Each subsection (h2) describes the version of that concept. For example: You may choose to put all Windows service-based persistence documentation under the same document, then have different methods of creating services (e.g. sc.exe, reg.exe, etc) as each subsection. 

The numeric identifier in the subsection title is used alongside the guid value in the metadata as the combined identifier. This identifier is used by the mapping file to indicate which guidance subsection to include in the final operator notebook.

```
### Prerequisites
### Guidance
### Cleanup
### Notes
### References
```

The remaining h3 headings are standard sections for each version. All are considered optional but a minimum of one must be included under every h2 section.

## Operator Notebook

The merged document ("operator notebook") is organized by campaign, with Blueprint-level guidance going under a "General" section.
When documents are merged, the content is flattened. The primary header and description are merged with the selected subsection header and description then the heading sizes are decreased and placed under the appropriate campaign in the merged document. 

For example, the following document

```
---
x_guidance_id: 00000000-0000-0000-0000-000000000000
gsv: 1
---

# General title

General description

## [1] Version Title

Version description

### Guidance

> command.exe
```

will transform into

```
# Campaign

## General title - Version Title

General description

Version description

### Guidance

> command.exe
```

as part of the merged document.


## Mapping file

The mapping file is a YAML document that maps variant IDs to a list of guidance document IDs + subsections. The schema for the mapping file is 

```yaml
<guid>: 
- Map!
```

map: 

```yaml
id: String!
entry: Integer!
scope: String
```

Example:

```yaml
30500c37-e898-4c62-a0e4-c4ce2fedc473:
- id: ba172c9d-a689-4367-a5e2-1d20c75f37a6
  entry: 1
```

where `30500c37-e898-4c62-a0e4-c4ce2fedc473` is the variant ID, `ba172c9d-a689-4367-a5e2-1d20c75f37a6` is the guidance ID, and `1` is the guidance subsection.

Additionally, you can map guidance to a Blueprint by providing the Blueprint ID in place of the Variant ID. Guidance mapped to a Blueprint will be placed under a `General` section rather than a specific campaign section.

`scope` defines the guidance scope (only one scope; see below).

## Guidance Scopes

Guidance scopes allow you to restrict when operator guidance appears in the merged notebook (and in the [linked data table](../Extensions.md)). Scopes are arbitrary strings.

By default, all document are scoped to the `default` scope. 

If you provide a `scope` property in the mapping, the guidance in that mapping entry will only be included when that scope is enabled via the scope setting.
Scopes work additively, so providing multiple scopes will include all documents matching any of the scopes.

Example:

```yaml
b2f7345d-aeb5-45a2-813f-79d87f42fbbf:
- id: 304a3673-34d7-4fa4-94e4-39645d1c8802
  entry: 1
- id: 45dc5351-5ff9-4128-9dd3-4b3f36cb79b5
  entry: 1
  scope: internal
0f3342ca-9104-4a5a-bcec-17869714eb22:
- id: a569918c-a1a4-482d-b5db-b3607eea777c
  entry: 1
```
Run #1: 
- Scope: *unspecified*
- Result: Notebook contains only 304a3673-34d7-4fa4-94e4-39645d1c8802#1 and a569918c-a1a4-482d-b5db-b3607eea777c#1

Run #2: 
- Scope: internal
- Result: Notebook contains only 45dc5351-5ff9-4128-9dd3-4b3f36cb79b5#1

Run #3: 
- Scope: internal, default
- Result: Notebook contains all three items

## Settings

|Arg|Variable|Description|Notes|
|---|---|---|---|
||LIBMM_GUIDANCE_PATHS|":"-delimited list of paths for guidance documents||
||LIBMM_GUIDANCE_MAPPING|Path to mappings file||
|--guidance-opnotebook|LIBMM_GUIDANCE_OPNOTEBOOK|Path to output Markdown file||
|--guidance-scopes|LIBMM_GUIDANCE_SCOPES|Comma-separated list of scopes|Defaults to "default"|

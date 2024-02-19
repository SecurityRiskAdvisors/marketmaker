# Partials Extension

This extension allows the use of canned block/detect list items by storing thsoe canned strings in a standalone file and replacing them in the Variant with an identifier. 

## Details

The list items in the `block`/`detect` sections can optionally be identifiers for "partials". "Partials" are canned strings that are meant to be reused across Variants in order to ensure consistency in exported documents. For example, if you have 10 local discovery test cases using builtin Windows discovery tools, rather than writing the same block/detect guidance for all of them you can write it once then have the Variants use an identifier. During the export process, the identifier strings are replaced with the actual content.

To use partials:

1. Create a partials document, a YAML document of arbitrary key-value pairs with an arbitrary nesting-level
2. In the block/detect sections, add an identifier for the partial. The partials identifier is a "."-delimited string of the key and is prefixed with the static string (default is `partial::`).

*Example*

Partial document:

```
endpoint:
  signature:
    detect: "Example endpoint signature detection"
general:
  signature: "Example general signature"
```

Partial used in Variant:

```
block:
- 'partial::general.signature'
detect:
- 'partial::endpoint.signature.detect'
```

In the exported document, the `block`/`detect` sections will be rendered as:

```
block:
- Example general signature
detect:
- Example endpoint signature detection
```

## Settings

|Arg|Variable|Description|Notes|
|---|---|---|---|
||LIBMM_PARTIALS_FILE|Path to YAML document with partials definitions|Does not expose a CLI arg|

# MM CLI

The `mm-cli` CLI is installed by default when you install the `libmm` package.

The CLI provides the following subcommands:

- `generate` used for generating Variant resources like manifests
- `compare` used for comparing multiple blueprints
- `util` for misc utility commands

## Usage - Generate

```
Usage: mm-cli generate [OPTIONS]

Options:
  -t, --technique-paths TEXT  One or more paths to technique directories.
                              Concatenate paths with a ':'. For example:
                              /foo:/bar. Defaults to 'techniques/'  [required]
  -b, --blueprint FILE        path to blueprint   [required]
  -o, --output FILE           Merged Index YAML output file
  -s, --summary FILE          Summary CSV output file
  -n, --navigator FILE        MITRE Navigator layer output file
  -i, --sublibrary DIRECTORY  Sublibrary directory
  --help                      Show this message and exit.
  <extension-specific options>
```

`--output` will create a Manifest YAML document.
`--summary` will create a CSV summary document containing the Variant names, descriptions, campaigns, and MITRE Technique IDs.
`--navigator` will create a MITRE Navigator layer JSON document.
`--sublibrary` will create a sublibrary export of the Variants in the blueprint at the path specified. 

The sublibrary will be organized by campaign name and the exported Variants will be named based on their IDs.

Refer to [extension documentation](extensions) directory for extension-specific documentation.

## Usage - Compare

```
Usage: mm-cli compare [OPTIONS]

Options:
  -t, --technique-paths TEXT  One or more paths to technique directories.
                              Concatenate paths with a ':'. For example:
                              /foo:/bar. Defaults to 'techniques/'  [required]
  -b1, --blueprint1 FILE      path to blueprint 1  [required]
  -b2, --blueprint2 FILE      path to blueprint 2  [required]
  -n, --navigator FILE        Comparison MITRE Navigator layer output file
  --stats                     Print stats for overlap
  --help                      Show this message and exit.
```

`--navigator` will create a MITRE Navigator layer JSON document with both blueprints' Variants. 
Techniques only in blueprint 1 will be colored blue, techniques only in blueprint 2 will be colored red, and techniques
in both blueprints will be colored purple.

`--stats` will output to `stdout` two percentages. The "Variant overlap" percentage is the percent of test cases
that share the same Technique ID and Variant name (but not necessarily the same version). The "MITRE overlap" percentage
is the percent of test cases that share the same Technique and Tactic IDs. 
In either case, the denominator is the set of all pairs. 
As a simplified example: If blueprint 1 has test cases { 1, 2, 3 } and blueprint 2 has test cases { 2, 3, 4 }, then
the stat will display a 50% overlap since the total test case list is { 1, 2, 3, 4 } and { 2, 3 } appear in both (2/4 = 0.5).
When calculating real-world overlap, keep in mind that a manual approach is required to determine if test cases
across blueprints can be considered as proxies for one another. 
This command is only meant to provide a very rough approximation as a starting point.

## Usage - Util

## defend subcommand 

```
Usage: mm-cli util defend [OPTIONS]

Options:
  -t, --tid TEXT  Technique ID  [required]
  --help          Show this message and exit.
```

Returns the MITRE D3FEND offensive artifact(s) for the given MITRE ATT&CK TID

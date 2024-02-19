# Sigma Extension

This extension generates a document containing Sigma rules that are mapped to Variants in a Blueprint. Rules can be loaded from a local repository or directly from GitHub.

## Document format

The generated document is a markdown file that uses the following structure per test case

````
# <test case name>

ID: <Variant ID>

### Rule

```yaml
<sigma rule>
```
````

## Mapping file

The mapping file is a YAML document that maps variant IDs to Sigma rule ID(s). The schema for the mapping file is 

```yaml
<guid>: List!
```

Where the list of one or more Sigma rule IDs and `<guid>` is the Variant ID


## Settings

|Arg|Variable|Description|Notes|
|---|---|---|---|
||LIBMM_SIGMA_MAPPING|Path to mappings file||
||LIBMM_SIGMA_RULES|Path to one or rule directories (":") delimited||
|--sigma-path|LIBMM_SIGMA_PATH|Path to output Markdown file||

### GitHub auto-download

If you would like the extension to pull the latest release of the core++ rules zip from GitHub rather than use a local directory of rules, set the value of `--sigma-rules`/`LIBMM_SIGMA_RULES` to `latest`. The zip will be downloaded into a temporary directory, loaded, then deleted.


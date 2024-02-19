# Manifests

Manifests are the exported test case lists that are intended to be ingested into other tools for use in execution.

## Schema

They follow the structure:

```
metadata: Map!
campaign name: Map[]!
```

Where `metadata` is a key-value mapping. If using with VECTR, use the following metadata:

```
metadata:
  prefix: String!
  bundle: String!
```

Where `prefix` is the prefix test case templates will be given for the template management sections of VECTR and `bundle` is the Assessment Group template name the test cases will be grouped under. These are the same as `prefix` and `assessment` in the Blueprint.

Each campaign should be included as a top-level key with its contents being a list of Variant mappings. For example:

```
Initial Access:
- name: Malicious Email
  description: Malicious email description
  ...
```
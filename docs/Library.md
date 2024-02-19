# Test Case Library

Market Maker based tools expect a Variant library with the following directory structure:

```
directory
\_ MITRE technique ID
    \_ variant
        \_ version
```

Where `variant` is an arbirtary identifier and `version` is the file containing the test case and has a file name of format `v<#>.yml`.

For example:

```
techniques
\_ T1003.001
    \_ procdump
        \_ v1.yml
```

This test case would be found at `techniques/T1003.001/procdump/v1.yml`.


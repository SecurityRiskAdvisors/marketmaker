# Developer Notes

This page describes considerations `libmm` developers should make when using it outside the exposed user utilities like the CLI.

## Variant <-> Entry references

Variant objects should generally maintain a reference to the technique library file backing it via the `filepath` attribute.
This is automatically set when using the `Variant.from_file(...)` classmethod.


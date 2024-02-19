# Environment Variables

The following environment variables can be used to control `libmm` settings:

|Variable|Type|Description|Default|Notes|
|---|---|---|---|---|
|LIBMM_LOGFILE_PATH|String|Log file path|.mm.log||
|LIBMM_RUN_CHECKS|Boolean|Enable runtime validation checks|True||
|LIBMM_ADD_D3FEND|Boolean|Add D3FEND artifacts and countermeasures to exported Variants|False||
|LIBMM_ADD_GROUPS|Boolean|Add group metadata to exported Variants|False||
|LIBMM_DISABLE_EXTENSIONS|Boolean|Disable extensions and event emission|False||
|LIBMM_EXTENSIONS_DIRECTORY|String|Path to extensions directory|||
|LIBMM_DB_FILEPATH|String|Use on-disk SQLite database rather than in-memory|||
|LIBMM_DB_DELIMETER|String|Default delimiter to use for SerDe operations|\|\||When using the same database across runs, this value must not change|
|LIBMM_DB_AUTODELETE|Boolean|If using an on-disk database, delete it before use|True||


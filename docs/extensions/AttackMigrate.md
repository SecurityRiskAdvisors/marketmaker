# ATT&CK Migrate 

This extension modifies rendered Variants to migrate revoked ATT&CK Techniques.

When in pre-v19 mode, the revocations are based on a manual mapping within th extension.

When not in pre-v19 mode, you can enable the v19 crosswalk to migrate Techniques and Tactics based on MITRE's ATT&CK v19 crosswalk file (https://attack.mitre.org/docs/subtechniques/de-split-crosswalk.json).

## Settings

|Arg|Variable|Description|Notes|
|---|---|---|---|
||LIBMM_ATTACKMIGRATE_V19CROSSWALK|Enable automatic Technique and Tactic changes based on the MITRE crosswalk|Only applies when not in pre-v19 mode.|

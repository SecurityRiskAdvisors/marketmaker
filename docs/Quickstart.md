# Quickstart Guide

This document covers the basic use of Market Maker to create a threat plan.

## Setup

1. Install Python 3
2. Create a virtual environment using your preferred method
3. Install Market Maker (`pip install marketmaker`)

## Prepare Test Cases 

Each test case is represented in Market Maker as a Variant file and the specific schema is defined in [Variant.md](Variants.md). 

Prepare one or more test cases per the schema. You can use the [SRA Indexes repo](https://github.com/SecurityRiskAdvisors/indexes) as a starting point. For example, a scheduled task persistence Variant might look like:

```yaml
name: Persist via new scheduled task
description: Persist on a system by creating a new scheduled task
platforms:
- windows
guidance:
- cmd> schtasks.exe /create /sc daily /tn {{ task_name }} /tr {{ command }} /st 20:00
block:
- Suspicious process execution/behavior blocked by endpoint security tool
detect:
- Suspicious process execution/behavior detected by endpoint security tool
- Use scheduled task creation events (Event ID 4698) to identify newly created scheduled tasks. Look specifically for events that are anomalous as compared to other task creation events in the environment, such as events where the command is unique across all other tasks and events created by principals that do not commonly create tasks.
controls:
- SIEM
- Endpoint Protection
metadata:
  id: 20a6dace-d801-42f5-b659-6cf91e39d273
  tid: T1053.005
  tactic: TA0003
``` 

*source: https://github.com/SecurityRiskAdvisors/indexes/blob/master/fs-index-2024/techniques/Persistence/20a6dace-d801-42f5-b659-6cf91e39d273.yml*

## Prepare Library

The library is a directory of test cases that are shared by all threat plans. Market Maker expects a specific directory structure for the library as detailed in [Library.md](Library.md).

Using the above scheduled task example, the file should be stored at:

`techniques` / `T1053.005` / `schtasks` / `v1.yml`

assuming it is the first version for `schtasks` in your library.

## Blueprint

The Blueprint file sets the Variants to be included in the generated plan as well as any associated metadata for the plan.

A test plan containing the scheduled task persistence might look like

```yaml
name: My first plan
description: Example test plan

metadata:
  id: e2edc166-31b6-45fd-a41a-ec7971635f61
  vectr:
    prefix: "MFP"
    assessment: "My first plan"

campaigns:
  Persistence:
    T1053.005:
      schtasks: 1
```

- The `id` is a UUID and should not overlap with other Blueprint UUIDs
- The `vectr` section specifies the [VECTR](https://vectr.io/) assessment template details. This is optional if the generated plan won't be used in VECTR.
- The `campaigns` specifies how the test cases should be organized. Campaigns are essentially containers for test cases and the names are arbitrary.
- Each campaign specifies the test cases to include by one of the accepted lookup criteria (see [Variants.md](Variants.md)). For the scheduled task test case, this is done via the MITRE technique ID, Variant name, and Variant version. This criteria mirrors the Variant's path within the library.

## Generate plan

Once all of the above pieces are in place, you can generate the plan using the `mm-cli` command from your virtualenv. Refer to [Cli.md](Cli.md) for full usage information and output formats.

Command:

```
mm-cli generate -t techniques/ -b blueprint.yml -o plan.yml
```

Replace `techniques/` with the path to your library, `blueprint.yml` with the name of your Blueprint file, and `plan.yml` with your output file name.



***

# Version 1.11.0 - June 2025

- Updates to Darkpool viewer:
  - Added a text search to the test case listing page for searching through test case names, descriptions, and commands
  - Added a new endpoint `/search-index.json` that includes all Variants in their rendered form for use by the search function
- Switched from CommonMark to [Marked](https://github.com/markedjs/marked) for Markdown rendering. This should allow for use of GitHub-flavored Markdown in [guidance documents](docs/extensions/Guidance.md).
- Bug fix for Guidance extension when splitting then rejoining source documents
- MITRE data refresh

***

# Version 1.10.0 - April 2025

- Updates to Darkpool viewer:
  - include Variant tools/references on Variant pages
  - sort Variant list by MITRE TID
  - HTML titles mirror the page titles
- MITRE data refresh

***

# Version 1.9.0 - April 2025

- Added extension to modify revoked Technique IDs in Variants (`libmm/extensions/attackmigrate.py`)

***

# Version 1.8.1 - December 2024

- Added support for overriding multiple version of the same Variant via the Blueprint

***

# Version 1.8.0 - December 2024

- Added support for Blueprint overrides to Darkpool
- Fixed prerequisites list in Darkpool

***

# Version 1.7.2 - November 2024

- Added back scoping check

***

# Version 1.7.1 - November 2024

- Fix bug in Guidance extension for duplicates in linked data

***

# Version 1.7.0 - November 2024

- Added summary CSV download button to Darkpool
- Added scoping functionality to Guidance extension

***

# Version 1.6.0 - November 2024

- Fix multiple bugs in Guidance extension
- Fix spacing issues in Darkpool Markdown

***

# Version 1.5.2 - October 2024

- Fix bug with overrides not applying for CSV output

***

# Version 1.5.1 - October 2024

- Fix bug with overrides applying incorrectly 

***

# Version 1.5.0 - August 2024

- Fix bug with extensions when using linked data

***

# Version 1.4.0 - July 2024

- Added a new linked data format ("Unformatted") 

***

# Version 1.3.0 - July 2024

- Update data resources
- Fix bug in Navigator layer generation

***

# Version 1.2.0 - March 2024

- Added Darkpool script for generating static HTML sites of library

***

# Version 1.1.0 - March 2024

- Added Selectors experimental functionality

***

# Version 1.0.1 - February 2024

- Update linked data for Guidance extension
- Log errors for Variant ingest
- Sort Manifest to have metadata first

***

# Version 1.0.0 - February 2024

- Initial release

***


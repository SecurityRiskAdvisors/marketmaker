message="changes"
datadir=libmm/data
d3fendjsonurl=https://d3fend.mitre.org/api/ontology/inference/d3fend-full-mappings.json
d3fendjsonpath=$(datadir)/d3fend.json
ctijsonurl=https://github.com/mitre/cti/blob/master/enterprise-attack/enterprise-attack.json?raw=true
ctijsonpath=$(datadir)/enterprise.json
ctitidpath=$(datadir)/tids.txt
# https://python-poetry.org/docs/cli/#version
# 	major	1.3.0	2.0.0
# 	minor	2.1.4	2.2.0
# 	patch	4.1.1	4.1.2
bumprule="patch"

format:
	poetry run black -l 120 libmm/

dependencies:
	poetry install --all-extras --quiet --no-root --with dev

.PHONY: dist
dist: format
	mkdir -p dist
	rm dist/* || true
	poetry version $(bumprule)
	poetry build -f wheel

git:
	$(eval branch := $(shell git branch --show-current))
	git add .
	git commit -a -m "$(message)"
	git push origin $(branch)

ensure_datadir:
	mkdir -p "$(datadir)"

dl_d3fend: ensure_datadir
	curl -fsSL "$(d3fendjsonurl)" -o "$(d3fendjsonpath)"

dl_enterprise_cti: ensure_datadir
	curl -fsSL "$(ctijsonurl)" -o "$(ctijsonpath)"

tids_from_cti: dl_enterprise_cti
	jq . "$(ctijsonpath)" | grep "external_id\": \"T1" | cut -d '"' -f 4 | sort -u > "$(ctitidpath)"

create_data_resources: dl_d3fend tids_from_cti

push: format git

update_push: create_data_resources dist git 

setup_and_build:
	apt update && apt install -y build-essential curl jq python3-pip python3-venv
	# symlink version python to just python to avoid changes to Makefile
	ln -s /usr/bin/python3 /usr/bin/python
	# setup poetry via pipx
	python -m pip install --user pipx
	python -m pipx ensurepath --force
	python -m pipx install poetry
	export PATH="$HOME/.local/bin:$PATH"
	# install python deps then build the wheel
	$(MAKE) dependencies update_push message="CI build"


gha:
	# all build deps should be covered by GHA ubuntu-latest/22.04 image
	pip install poetry
	# install python deps then build the wheel
	$(MAKE) dependencies update_push message="CI build"


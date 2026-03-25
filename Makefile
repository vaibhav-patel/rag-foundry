.PHONY: fmt lint test cdk-synth install

install:
	python3 -m pip install -U pip ruff pytest
	python3 -m pip install -e "packages/sdk-python" -e "infra/[dev]" -e "services/control_plane/[dev]" -e "packages/contracts" -e "cli/[dev]"

fmt:
	ruff format services/control_plane services/workers/lambda_stub infra cli packages/contracts packages/sdk-python scripts
	ruff check --fix services/control_plane services/workers/lambda_stub infra cli packages/contracts packages/sdk-python scripts

lint:
	ruff check services/control_plane services/workers/lambda_stub infra cli packages/contracts packages/sdk-python scripts

test:
	pytest -q

cdk-synth:
	cd infra && cdk synth -q

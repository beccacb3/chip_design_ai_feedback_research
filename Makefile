IMAGE  = spec-fidelity
CONFIG ?= configs/experiments/baseline.yaml

# Run a command inside the Docker container with the repo (and ~/.tokens if present) mounted.
DOCKER = docker run --rm -v $(CURDIR):/work -v $(HOME)/.tokens:/root/.tokens:ro -w /work -e PYTHONPATH=/work -e PYTHONDONTWRITEBYTECODE=1 -e OPENROUTER_API_KEY -e OPENROUTER_TOKEN_FILE $(IMAGE)

.PHONY: image shell check show-config test run eval report

image:              ## Build the Docker image (Python + iverilog + verilator)
	docker build -t $(IMAGE) .

shell:              ## Open a bash shell inside the container
	docker run --rm -it -v $(CURDIR):/work -w /work -e PYTHONPATH=/work -e OPENROUTER_API_KEY $(IMAGE) bash

check:              ## Check design folders and experiment configs
	python3 designs/standardize.py check
	python3 -m framework.config $(CONFIG) > /dev/null

show-config:        ## Print the resolved ExperimentConfig for CONFIG
	python3 -m framework.config $(CONFIG)

test:               ## Run infrastructure unit/integration tests in Docker
	$(DOCKER) python3 tests/test_simulation.py
	$(DOCKER) python3 tests/test_testing_and_feedback.py
	$(DOCKER) python3 tests/test_llm.py

run:                ## Run an experiment into a new folder in runs/
	$(DOCKER) python3 -m framework.control_loop $(CONFIG)

eval:               ## Score a saved run against designs/.../golden/
	$(DOCKER) python3 -m evaluation.final $(RUN)

report:             ## Build a comparison table across runs/
	$(DOCKER) python3 -m evaluation.report runs/

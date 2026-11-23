IMAGE  = spec-fidelity
CONFIG ?= configs/experiments/e1_monolithic.yaml

# Run a command inside the Docker container as the current user with the repo and ~/.tokens mounted.
DOCKER = docker run --rm -u $(shell id -u):$(shell id -g) -v $(CURDIR):/work -v $(HOME)/.tokens:$(HOME)/.tokens:ro -w /work -e HOME=$(HOME) -e PYTHONPATH=/work -e PYTHONDONTWRITEBYTECODE=1 -e OPENROUTER_API_KEY -e OPENROUTER_TOKEN_FILE $(IMAGE)

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
	$(DOCKER) python3 tests/test_control_loop_and_final.py
	$(DOCKER) python3 tests/test_llm.py

run:                ## Run an experiment into a new folder in runs/
	$(DOCKER) python3 -m framework.control_loop $(CONFIG)

eval:               ## Re-run the final evaluation stage on a saved run folder
	$(DOCKER) python3 -m framework.control_loop --eval-only $(RUN)

report:             ## Build a comparison table across runs/
	$(DOCKER) python3 -m evaluation.report runs/

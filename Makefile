IMAGE  = spec-fidelity
CONFIG ?= configs/experiments/baseline.yaml

# Run a command inside the Docker container with the repo mounted.
DOCKER = docker run --rm -v $(PWD):/work -w /work -e OPENROUTER_API_KEY $(IMAGE)

.PHONY: image shell check show-config run eval report

image:              ## Build the Docker image (Python + iverilog + verilator)
	docker build -t $(IMAGE) .

shell:              ## Open a bash shell inside the container
	docker run --rm -it -v $(PWD):/work -w /work -e OPENROUTER_API_KEY $(IMAGE) bash

check:              ## Check design folders and experiment configs (runs locally or via DOCKER)
	python3 scripts/standardize.py check
	python3 scripts/show_config.py $(CONFIG) > /dev/null

show-config:        ## Print the resolved ExperimentConfig for CONFIG
	python3 scripts/show_config.py $(CONFIG)

run:                ## Run an experiment into a new folder in runs/ (not implemented yet)
	$(DOCKER) python3 scripts/run_experiment.py $(CONFIG)

eval:               ## Score a saved run against designs/.../golden/ (not implemented yet)
	$(DOCKER) python3 scripts/evaluate.py $(RUN)

report:             ## Build a comparison table across runs/ (not implemented yet)
	$(DOCKER) python3 scripts/report.py runs/

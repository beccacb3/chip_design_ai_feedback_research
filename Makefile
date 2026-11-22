IMAGE  = spec-fidelity
CONFIG ?= configs/experiments/baseline.yaml

# Run a command inside the Docker container with the repo mounted.
DOCKER = docker run --rm -v $(PWD):/work -w /work -e OPENROUTER_API_KEY $(IMAGE)

.PHONY: image shell check show-config run eval report

image:              ## Build the Docker image (Python + iverilog + verilator)
	docker build -t $(IMAGE) .

shell:              ## Open a bash shell inside the container
	docker run --rm -it -v $(PWD):/work -w /work -e OPENROUTER_API_KEY $(IMAGE) bash

check:              ## Check design folders and experiment configs
	python3 designs/standardize.py check
	python3 -m framework.config $(CONFIG) > /dev/null

show-config:        ## Print the resolved ExperimentConfig for CONFIG
	python3 -m framework.config $(CONFIG)

run:                ## Run an experiment into a new folder in runs/
	$(DOCKER) python3 -m framework.control_loop $(CONFIG)

eval:               ## Score a saved run against designs/.../golden/
	$(DOCKER) python3 -m evaluation.final $(RUN)

report:             ## Build a comparison table across runs/
	$(DOCKER) python3 -m evaluation.report runs/

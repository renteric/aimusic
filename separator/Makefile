# Makefile with common development and deployment commands

.PHONY: help docker-build docker-up docker-down run

help:
	@echo "Available targets:"
	@echo "  docker-build   Build the container image"
	@echo "  docker-up      Start service with docker compose"
	@echo "  docker-down    Stop service and remove containers"
	@echo "  run            Run the API locally (requires virtualenv)"

# build the image using the Dockerfile
docker-build:
	docker compose build

# start the stack in detached mode
docker-up:
	docker compose up -d

# stop and remove the containers
docker-down:
	docker compose down

# run the API on the host (for development)
run:
	source venv/bin/activate && python src/api.py

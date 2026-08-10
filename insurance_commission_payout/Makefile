.PHONY: help install test lint format clean deploy

help:
	@echo "Commission Payout Pipeline - Available Commands"
	@echo "=============================================="
	@echo "make install       - Install dependencies"
	@echo "make test          - Run unit tests"
	@echo "make test-cov      - Run tests with coverage"
	@echo "make lint          - Run linting checks"
	@echo "make format        - Format code with black"
	@echo "make clean         - Clean up build artifacts"
	@echo "make lambda-build   - Build Lambda deployment package"
	@echo "make deploy        - Deploy using Terraform"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=glue/shared --cov=lambda --cov-report=html

lint:
	flake8 glue/ lambda/ tests/
	mypy glue/ lambda/

format:
	black glue/ lambda/ tests/
	isort glue/ lambda/ tests/

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf build/ dist/ *.egg-info/
	rm -rf .coverage htmlcov/
	rm -rf .pytest_cache/ .mypy_cache/

lambda-build:
	@echo "Building Lambda deployment package..."
	mkdir -p build/
	cd lambda/file_ingestion_audit && \
	pip install -r ../../requirements.txt -t ./package && \
	cp lambda_function.py ./package/ && \
	cd package && \
	zip -r ../../../build/lambda_function.zip . && \
	cd ../../../

deploy:
	@echo "Deploying infrastructure with Terraform..."
	cd infra/terraform && \
	terraform init && \
	terraform plan && \
	terraform apply

deploy-dry:
	@echo "Planning infrastructure deployment..."
	cd infra/terraform && \
	terraform init && \
	terraform plan

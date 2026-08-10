"""Setup configuration for package."""

from setuptools import setup, find_packages

setup(
    name="commission-payout-pipeline",
    version="1.0.0",
    description="AWS Lambda + Glue pipeline for insurance commission payout processing",
    author="Data Engineering Team",
    author_email="dataeng@company.com",
    url="https://github.com/company/commission-payout-pipeline",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "boto3>=1.26.0",
        "pandas>=1.5.0",
        "pgpy>=0.6.0",
        "aws-lambda-powertools>=2.0.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.0.0",
            "mypy>=1.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
)

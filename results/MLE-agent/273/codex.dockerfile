FROM python:3.12-slim

# Install system dependencies for Python packages
RUN apt-get update && apt-get install -y     build-essential     gcc     libffi-dev     libssl-dev     python3-dev     curl     && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . /app

# Upgrade pip
RUN python -m pip install --upgrade pip

# Install setuptools and wheel (for pyproject.toml)
RUN pip install setuptools wheel

# Install Python dependencies from pyproject.toml
RUN pip install .

# Run test script by default
CMD ["python", "tests/test273.py"]

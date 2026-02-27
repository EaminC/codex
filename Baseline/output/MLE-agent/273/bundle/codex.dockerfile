FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     curl     && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only pyproject.toml to leverage Docker cache for deps
COPY pyproject.toml ./

# Install poetry to handle dependency installation
RUN pip install poetry

# Install dependencies with Poetry
RUN poetry config virtualenvs.create false && poetry install --no-root

# Copy all source files
COPY . /app

# Default command to run standalone Python script
CMD ["python", "test273.py"]

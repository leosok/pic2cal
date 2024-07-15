# use python-slim as base image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install poetry and dependencies
RUN pip install poetry==1.4.2
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --without dev

# Copy the source code into the container
COPY . .

# Run the application
CMD ["python", "bot-i.py"]
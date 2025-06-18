# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies
# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
# We'll copy main.py, the src directory, and the scripts directory for the Streamlit UI
COPY main.py .
COPY src/ ./src/
COPY scripts/ ./scripts/

# Make port 80 available to the world outside this container (if your app were a web server)
# EXPOSE 80 
# Expose port 5001 for the health check server
EXPOSE 5001

# Define the command to run your app
# This will execute when the container starts
CMD ["python", "main.py"]

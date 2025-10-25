# Use a slim version of the official Python image as the base image
FROM python:3.13-slim-bookworm

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements.txt file to the container
COPY requirements.txt .

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code to the container
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Expose a port (Optional: Only needed if using HTTP servers or health checks)
EXPOSE 8080

# Run the bot using the command
CMD ["python", "main.py"]
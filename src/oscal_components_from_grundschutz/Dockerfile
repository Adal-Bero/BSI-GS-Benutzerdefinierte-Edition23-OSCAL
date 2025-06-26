# Dockerfile

# Use an official lightweight Python 3.11 image.
FROM python:3.11-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file and install dependencies first.
# This step is cached by Docker, speeding up future builds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all your other files (main.py, prompt.txt, bsi_gk_2023_oscal_schema.json)
# into the container's working directory.
COPY . .

# This is the crucial command.
# It tells the container to simply run your Python script and then exit.
# The "-u" flag is important for Cloud Run jobs as it ensures logs are
# sent immediately without being buffered.
CMD ["python", "-u", "main.py"]
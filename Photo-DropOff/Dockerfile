FROM python:3.12-slim

WORKDIR /app

# System deps (uncomment if a project needs Pillow/image processing etc.)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Match each app's real port
EXPOSE 5003

# If app.py does app.run(host="0.0.0.0", port=5000), this is enough:
CMD ["python3", "app.py"]

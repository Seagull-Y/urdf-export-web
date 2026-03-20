FROM python:3.11-slim

WORKDIR /app

# System deps needed by onshape-to-robot mesh processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements_web.txt .
RUN pip install --no-cache-dir -r requirements_web.txt

# App source
COPY . .

# Runtime directories (also mapped as volumes in compose)
RUN mkdir -p static jobs

EXPOSE 8000

# Single worker: BackgroundTasks share in-process JOBS dict
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

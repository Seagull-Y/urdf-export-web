FROM python:3.11-slim

WORKDIR /app

# System deps needed by onshape-to-robot mesh processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements_web.txt .
RUN pip install --no-cache-dir -r requirements_web.txt

# App source (includes patch_library.py)
COPY . .

# Patch onshape-to-robot: handle parts with no material (missing mass/centroid/inertia)
# so the export doesn't crash — zero mass is written to URDF and flagged in the UI.
RUN python3 patch_library.py

# Runtime directories (also mapped as volumes in compose)
RUN mkdir -p static jobs

EXPOSE 8000

# Single worker: BackgroundTasks share in-process JOBS dict
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

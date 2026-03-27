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

# Patch onshape-to-robot: handle parts with no material (missing mass/centroid/inertia)
# so the export doesn't crash — zero mass is written to URDF and flagged in the UI.
RUN python3 -c "
import pathlib, site
for d in site.getsitepackages():
    p = pathlib.Path(d) / 'onshape_to_robot' / 'robot_builder.py'
    if p.exists():
        c = p.read_text()
        patched = c
        patched = patched.replace('mass_properties[\"mass\"]',     'mass_properties.get(\"mass\",     [0.0])')
        patched = patched.replace('mass_properties[\"centroid\"]', 'mass_properties.get(\"centroid\", [0.0, 0.0, 0.0, 0.0])')
        patched = patched.replace('mass_properties[\"inertia\"]',  'mass_properties.get(\"inertia\",  [0.0]*12)')
        if patched != c:
            p.write_text(patched)
            print(f'Patched {p}: parts without material export with zero mass')
        else:
            print(f'Patch already applied or pattern not found in {p}')
        break
"

# App source
COPY . .

# Runtime directories (also mapped as volumes in compose)
RUN mkdir -p static jobs

EXPOSE 8000

# Single worker: BackgroundTasks share in-process JOBS dict
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

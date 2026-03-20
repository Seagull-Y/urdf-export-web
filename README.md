# URDF Export Web

A web application that exports Onshape CAD assemblies to URDF format and previews the robot in an interactive 3D viewer.

## Features

- Export Onshape assemblies to URDF via API
- Interactive 3D preview with joint controls
- Per-link mass display panel
- Wireframe toggle and camera fit
- Docker-ready deployment

---

## Deployment Options

| Method | Best for |
|---|---|
| [Docker (recommended)](#docker-deployment-recommended) | Production servers, clean Ubuntu |
| [Local Python](#local-python-deployment) | Development / quick test |

---

## Docker Deployment (Recommended)

### 1. Install Docker on Ubuntu

```bash
sudo apt update && sudo apt install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt update && sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER && newgrp docker
```

Verify:
```bash
docker run hello-world
```

### 2. Clone the repository

```bash
sudo apt install -y git
git clone https://github.com/Seagull-Y/urdf-export-web.git
cd urdf-export-web
```

### 3. Configure API keys

```bash
cp .env.example .env
nano .env
```

Fill in your Onshape credentials:
```
ONSHAPE_ACCESS_KEY=your_access_key_here
ONSHAPE_SECRET_KEY=your_secret_key_here
```

> Get your keys at: https://cad.onshape.com/user/developer/apiKeys

### 4. Build and start

```bash
docker compose up --build -d
```

The app is available at `http://<server-ip>:8000`.

**Common commands:**
```bash
docker compose logs -f        # live logs
docker compose down           # stop
docker compose up -d          # start (after first build)
```

### 5. Open firewall port (if needed)

```bash
sudo ufw allow 8000/tcp
```

---

## Local Python Deployment

### 1. Install system dependencies

```bash
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv git \
    libgl1-mesa-glx libglib2.0-0 libgomp1
```

### 2. Clone the repository

```bash
git clone https://github.com/Seagull-Y/urdf-export-web.git
cd urdf-export-web
```

### 3. Create virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements_web.txt
```

### 4. Configure API keys

```bash
cp .env.example .env
nano .env
```

Fill in your Onshape credentials:
```
ONSHAPE_ACCESS_KEY=your_access_key_here
ONSHAPE_SECRET_KEY=your_secret_key_here
```

### 5. Run

```bash
python3 app.py
```

Open your browser at `http://localhost:8000` (or `http://<server-ip>:8000` from another machine).

---

## Project Structure

```
.
├── app.py                  # FastAPI web server
├── export_urdf.py          # Onshape → URDF export logic
├── static/
│   └── index.html          # Single-page frontend (Three.js viewer)
├── requirements_web.txt    # Web + export dependencies
├── Dockerfile
├── docker-compose.yml
└── .env.example            # Environment variable template
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ONSHAPE_ACCESS_KEY` | Yes* | Onshape API access key |
| `ONSHAPE_SECRET_KEY` | Yes* | Onshape API secret key |
| `PORT` | No | Server port (default: `8000`) |

\* Keys can also be entered per-export in the UI (and optionally saved in the browser).

---

## Usage

1. Open the web app and paste your Onshape document URL.
2. Enter your API keys (stored locally in the browser if "Remember on this machine" is checked).
3. Click **Export** to start the URDF export.
4. Once complete, the 3D preview loads automatically.
5. Use **Joint Controls** on the right panel to pose the robot.
6. Click **Download** to get the URDF package as a ZIP file.

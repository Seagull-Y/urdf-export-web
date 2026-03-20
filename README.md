# URDF Export Web

A web application that exports Onshape CAD assemblies to URDF format and previews the robot in an interactive 3D viewer.

## Features

- Export Onshape assemblies to URDF via API
- Interactive 3D preview with joint controls
- Per-link mass display panel
- Wireframe toggle and camera fit
- Docker-ready deployment

---

## Prerequisites

- Python 3.10+
- [Onshape API keys](https://cad.onshape.com/user/developer/apiKeys)
- (Optional) Docker & Docker Compose for containerized deployment

---

## Quick Start (Local)

### 1. Clone the repository

```bash
git clone https://github.com/Seagull-Y/urdf-export-web.git
cd urdf-export-web
```

### 2. Create a virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements_web.txt
```

### 3. Configure API keys

Create a `.env` file in the project root (see `.env.example`):

```bash
cp .env.example .env
```

Edit `.env` and fill in your Onshape API credentials:

```
ONSHAPE_ACCESS_KEY=your_access_key_here
ONSHAPE_SECRET_KEY=your_secret_key_here
```

> Get your keys at: https://cad.onshape.com/user/developer/apiKeys

### 4. Run the server

```bash
python app.py
```

Open your browser at `http://localhost:8000`.

---

## Docker Deployment

### 1. Configure environment

```bash
cp .env.example .env
# Edit .env with your Onshape keys
```

### 2. Build and start

```bash
docker compose up --build
```

The app will be available at `http://localhost:8000`.

### 3. Stop

```bash
docker compose down
```

---

## Project Structure

```
.
├── app.py                  # FastAPI web server
├── export_urdf.py          # Onshape → URDF export logic
├── static/
│   └── index.html          # Single-page frontend (Three.js viewer)
├── requirements.txt        # Export script dependencies
├── requirements_web.txt    # Web server dependencies
├── Dockerfile
├── docker-compose.yml
├── deploy.sh               # Production deploy helper
└── .env.example            # Environment variable template
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ONSHAPE_ACCESS_KEY` | Yes | Onshape API access key |
| `ONSHAPE_SECRET_KEY` | Yes | Onshape API secret key |
| `PORT` | No | Server port (default: `8000`) |

---

## Usage

1. Open the web app and paste your Onshape document URL.
2. Enter your API keys (stored locally in the browser if "Remember on this machine" is checked).
3. Click **Export** to start the URDF export.
4. Once complete, the 3D preview loads automatically.
5. Use **Joint Controls** on the right panel to pose the robot.
6. Click **Download** to get the URDF package as a ZIP file.

# URDF Export Web

A web application that exports Onshape CAD assemblies to URDF format and previews the robot in an interactive 3D viewer.

## Features

- Export Onshape assemblies to URDF via API
- **Parallel cache pre-warming** — fetches all part STLs concurrently (10 workers) before the main export, reducing download time 5–8×
- **Resume-style retry** — on network timeout, retries up to 3 times reusing already-cached parts (no re-download)
- Real-time export log with per-part download progress bar
- Interactive 3D preview with joint controls and per-link mass panel
- Parts without Onshape material assignment are flagged in the mass panel (shown as `0 g`) instead of crashing the export
- Usage statistics (daily / weekly / monthly exports)
- Auto-cleanup of export files older than 3 days
- Cloudflare Tunnel support for public HTTPS access
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

### 3. Configure environment

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

> **Permission note:** If you use an API key from a different Onshape account than the document owner, that account must be shared with **"Can copy"** permission or higher. "Can view" alone is insufficient for the STL export API and will return a 403 error.

### 4. Build and start

```bash
docker compose up --build -d
```

The app is available at `http://<server-ip>:8000`.

**Common commands:**
```bash
docker compose logs -f          # live logs
docker compose ps               # check container status
docker compose down             # stop all containers
docker compose up -d            # start (after first build)
```

### 5. Open firewall port (if needed)

```bash
sudo ufw allow 8000/tcp
```

---

## Public Access via Cloudflare Tunnel

`docker compose up` automatically starts a Cloudflare quick tunnel alongside the app.

### Option A — Quick tunnel (no account needed, URL changes on restart)

No configuration required. Check the public URL with:
```bash
docker logs urdf-cloudflared 2>&1 | grep -i trycloudflare
```

### Option B — Named tunnel with fixed domain

1. Sign up at [Cloudflare Zero Trust](https://one.dash.cloudflare.com) (free)
2. Go to **Networks → Tunnels → Create a tunnel → Cloudflared**
3. Name it (e.g. `urdf-web`) and copy the token
4. Add your domain in **Public Hostname**:
   - **Subdomain**: leave empty or use e.g. `urdf`
   - **Domain**: your domain (must be on Cloudflare DNS)
   - **Service**: `HTTP` → `urdf-exporter:8000`
5. Add the token to `.env` on the server:
   ```
   TUNNEL_TOKEN=eyJhIjoixxxxxxx
   ```
6. Restart:
   ```bash
   docker compose down && docker compose up -d
   ```

The tunnel automatically uses the named tunnel when `TUNNEL_TOKEN` is set, otherwise falls back to quick tunnel.

---

## Updating to a New Version

```bash
cd ~/urdf-export-web
git pull
docker compose up --build -d
```

If `Dockerfile` or `requirements_web.txt` changed, force a clean rebuild:
```bash
docker compose build --no-cache && docker compose up -d
```

To roll back:
```bash
git log --oneline          # find target commit
git checkout <commit-id>
docker compose up --build -d
```

---

## Local Python Deployment

### 1. Install system dependencies

```bash
sudo apt update && sudo apt install -y \
    python3 python3-pip python3-venv git \
    libgl1 libglib2.0-0 libgomp1
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

### 5. Run

```bash
python3 app.py
```

Open your browser at `http://localhost:8000`.

---

## Project Structure

```
.
├── app.py                  # FastAPI web server
├── export_urdf.py          # Onshape → URDF export logic (parallel pre-warm + retry)
├── patch_library.py        # Build-time patch: handles parts with no material (zero mass)
├── static/
│   └── index.html          # Single-page frontend (Three.js viewer)
├── requirements_web.txt    # Web + export dependencies
├── Dockerfile
├── docker-compose.yml
├── .env.example            # Environment variable template
└── jobs/                   # Export output (auto-cleaned after 3 days)
```

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `ONSHAPE_ACCESS_KEY` | Yes* | Onshape API access key |
| `ONSHAPE_SECRET_KEY` | Yes* | Onshape API secret key |
| `TUNNEL_TOKEN` | No | Cloudflare Tunnel token for fixed domain access |
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

# Server Portal — Design & Implementation

> Goal: A self-hosted web portal (frontend + backend) on your Ubuntu server (accessible via Tailscale 100.69.68.70:9090) to manage files, run commands, control a Minecraft server, and surface live system metrics (disk/CPU/RAM/temps/uptime). Grafana already available at `100.69.68.70:3000` and should be integrated for richer dashboards.

---

## High-level flowchart

```mermaid
flowchart LR
  Client[User browser]
  Client -->|HTTPS (Caddy)| Caddy[Caddy reverse proxy]
  Caddy --> Frontend[Static Frontend (Docker)]
  Caddy --> Backend[Backend API (FastAPI) (Docker)]
  Backend --> SQLite[SQLite DB (users, metadata)]
  Backend --> Storage[(Filesystem storage /srv/portal-storage)]
  Backend --> Minecraft[MC service (Docker or host)]
  Backend --> System[Host system (exec for commands, metrics)]
  Backend --> PromExporter[Prometheus metrics endpoint]
  PromExporter --> Grafana[Grafana @ 100.69.68.70:3000]
  Backend -->|optional| S3[MinIO or S3-compatible (optional)]

  subgraph Server[Ubuntu host 100.69.68.70]
    Caddy
    Frontend
    Backend
    SQLite
    Storage
    Minecraft
  end
```

---

## Tech stack (recommended)

* **Reverse proxy / TLS / static file server:** Caddy (automatic HTTPS; simple configuration)
* **Container runtime:** Docker (rootless is fine) + Docker Compose for orchestration
* **Backend:** **FastAPI** (Python) — fast to build, async, good WebSocket support for live terminal and metrics, easy Prometheus integration
* **Database:** SQLite (file on disk) for users and metadata (simple, local-only). Option to migrate to Postgres later.
* **Authentication:** JWT (access token) + salted password hashing (Argon2 or bcrypt). Seed an initial `root` user on first run.
* **Frontend:** Static HTML/CSS/JS (build with Vite / plain JS). Single-page app communicating with backend API + WebSocket for live terminal and metrics. Use plain JS + minimal framework (or React if you prefer) — but initially plain JS will be smaller and simpler.
* **File storage:** Host filesystem (e.g. `/srv/portal-storage/<username>`). Enforce *100 GB per user* by checking disk usage in the backend on uploads and on-demand.
* **Metrics/observability:** Expose Prometheus-compatible metrics from backend; Grafana (already running) will scrape backend for dashboards. Also optionally use node_exporter on host.
* **Optional:** MinIO (S3-compatible) if you want object storage in future.

---

## Project layout (repo)

```
server-portal/
├─ backend/
│  ├─ app/
│  │  ├─ main.py
│  │  ├─ api/
│  │  ├─ auth.py
│  │  ├─ storage.py
│  │  ├─ minecraft.py
│  │  └─ models.py
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/
│  ├─ index.html
│  ├─ src/
│  │  ├─ app.js
│  │  └─ styles.css
│  └─ Dockerfile
├─ caddy/
│  └─ Caddyfile
├─ docker-compose.yml
└─ docs/Server-portal-architecture.md   # this document
```

---

## Example `docker-compose.yml` (starter)

```yaml
version: '3.8'
services:
  caddy:
    image: caddy:latest
    restart: unless-stopped
    ports:
      - "9090:80"   # Tailscale port mapped externally (HTTP) - Caddy will handle TLS if public
      - "443:443"
    volumes:
      - ./caddy/Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - portal-net

  backend:
    build: ./backend
    container_name: portal-backend
    restart: unless-stopped
    environment:
      - DATABASE_URL=/data/portal.db
      - STORAGE_PATH=/data/storage
      - SECRET_KEY=replace_this_with_secure_random
    volumes:
      - portal_data:/data
      - /var/run/docker.sock:/var/run/docker.sock    # optional: to control dockerized minecraft
      - /sys/class/thermal:/sys/class/thermal:ro     # optional: for temperature sensors
    networks:
      - portal-net
    expose:
      - "8000"

  frontend:
    build: ./frontend
    container_name: portal-frontend
    restart: unless-stopped
    volumes:
      - ./frontend/dist:/usr/share/nginx/html:ro
    networks:
      - portal-net
    expose:
      - "80"

  minecraft:
    image: itzg/minecraft-server
    container_name: mc-server
    restart: unless-stopped
    environment:
      EULA: "TRUE"
      VERSION: "1.20.4"
    volumes:
      - /home/vincent/minecraft-server:/data
    ports:
      - "25565:25565"
    networks:
      - portal-net

volumes:
  portal_data:
  caddy_data:
  caddy_config:

networks:
  portal-net:
    driver: bridge
```

> Notes: you can run Minecraft either in its own Docker container (recommended for isolation) or keep running it from the host (you already have a `server.jar` and `world`). If you want to keep host-managed MC, remove the `minecraft` service and let the backend use system `subprocess` to start/stop with scripts (requires careful permission handling).

---

## Example `Caddyfile`

```
# Caddy listens on 9090 externally but manages routing internally
:9090 {
  encode gzip
  route /api/* {
    reverse_proxy backend:8000
  }

  route /ws/* {
    reverse_proxy backend:8000
  }

  handle_path / {
    root * /usr/share/nginx/html
    file_server
  }
}
```

If Caddy is publicly exposed and you want real TLS, use a domain (Caddy will use Let's Encrypt automatically). For Tailscale-only access, you can use `:80` and `:443` or keep the `:9090` mapping as you have.

---

## Backend design (FastAPI) — responsibilities

1. **Auth & Users**

   * Register user (username, full_name, email, password, password_repeat)
   * Login -> returns JWT access token
   * Admin root account seeded at first run
   * Password hashing: Argon2 or bcrypt (use `passlib`)

2. **File management**

   * Create user directory: `/data/storage/<username>`
   * Upload file(s) with streaming upload, check user quota before accepting
   * List files & folders
   * Download files (supports range requests for large files)
   * Delete files/folders (permission checks)
   * Move/rename

3. **Server commands**

   * `POST /api/exec` (admin-only or per-perm) — run safe sandboxed commands or scripts
   * Use restricted allowlist for dangerous ops (or require sudo via systemd wrappers)
   * WebSocket for interactive terminal (use `websockets` + `pty` package)

4. **Minecraft control**

   * `POST /api/minecraft/start` and `/stop` — either control docker container or call a systemctl script
   * `GET /api/minecraft/status` — returns `running|stopped`, player count, uptime

5. **Metrics**

   * Endpoint `/metrics` exposing Prometheus-style metrics (CPU, RAM, disk, per-user storage used, minecraft status)
   * Optionally forward metrics to node_exporter

6. **Admin actions**

   * Create user (or registration available publicly)
   * List users, reset password

---

## SQLite schema (starter)

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  full_name TEXT,
  email TEXT UNIQUE,
  password_hash TEXT NOT NULL,
  is_admin BOOLEAN DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  path TEXT NOT NULL,
  size INTEGER NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
```

> Implementation note: the `files` table is an index of stored files for quick quota calculations and listing. The truth is the filesystem, so run periodic reconciliation (cron job) to fix mismatches.

---

## Seeding initial `root` account (example Python snippet)

```python
# seed_admin.py
import sqlite3
from passlib.hash import argon2

conn = sqlite3.connect('/data/portal.db')
cur = conn.cursor()
# create tables if not exists (run migrations in real project)
# ...
username='root'
password='ChangeMeStrong!'
hash = argon2.hash(password)
cur.execute("INSERT OR IGNORE INTO users (username, full_name, email, password_hash, is_admin) VALUES (?, ?, ?, ?, 1)",
            (username, 'Root User', 'root@example.local', hash))
conn.commit()
conn.close()
```

**Important:** replace the default password immediately. You can instead accept `ROOT_PASSWORD` environment variable and run a bootstrap step in the container entrypoint.

---

## Enforcing 100 GB per user

Options:

1. **Application-level enforcement (recommended for simplicity)**

   * On upload, compute `current_used = du -sb /data/storage/<username>` or maintain `files` table and sum sizes.
   * If `current_used + incoming_size > 100*1024**3` reject upload with `413 Payload Too Large`.
   * Run a nightly job to recalculate and repair inconsistencies.

2. **Filesystem quotas** (more robust)

   * Use XFS or ext4 with project quotas or user quotas and assign a quota per user folder. This requires preparing the filesystem and is more involved.

For now, implement (1) in app code and add docs to migrate to (2) later.

---

## Minecraft control

You have two choices:

* **Dockerized**: use `itzg/minecraft-server` container (simple to start/stop from backend using Docker API). Pros: isolation, easy to snapshot volumes. Cons: port mapping management.

* **Host-managed**: keep your existing `/home/vincent/minecraft-server` and run `java -Xmx... -jar server.jar nogui` from systemd unit or managed script. Backend will call a wrapper script (must run as a user with permission).

**Example systemd unit (host-managed)**

```
[Unit]
Description=Minecraft Server
After=network.target

[Service]
User=vincent
Nice=1
WorkingDirectory=/home/vincent/minecraft-server
ExecStart=/usr/bin/java -Xmx4G -Xms1G -jar server.jar nogui
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Backend examples:

* To start/stop via systemd: `systemctl start mc-server.service` (if systemd unit created)
* To start/stop docker: use Docker SDK to start/stop container `mc-server`.

Be careful with permissions: backend container would need permission to control systemd or docker socket. Running docker socket inside backend grants a lot of power — secure the backend and only allow admin actions.

---

## API design (example routes)

* `POST /api/auth/register` — create user

* `POST /api/auth/login` — obtain JWT

* `GET /api/user/me` — profile

* `GET /api/files` — list

* `POST /api/files/upload` — upload file (streaming)

* `GET /api/files/download?path=...` — download

* `DELETE /api/files` — delete

* `POST /api/exec` — run allowed commands (body: { cmd: "ls -la" })

* `WS  /api/terminal` — interactive shell (authenticated + guarded)

* `POST /api/minecraft/start`  — start

* `POST /api/minecraft/stop`   — stop

* `GET  /api/minecraft/status` — status

* `GET /metrics` — Prometheus metrics

---

## Frontend responsibilities

* Authentication UI (login/register)
* File manager UI (upload, download, browse). Show user quota and used bytes.
* Minecraft control panel (start/stop/status + console tail)
* Terminal UI (WebSocket powered interactive terminal)
* Live metrics panel (CPU, RAM, disk, temps, uptime) — either directly via WebSocket from backend or via Grafana embedded panels (Grafana has embedding options).

**Grafana integration:** You can embed Grafana panels as `<iframe>` in the frontend, or link out to `100.69.68.70:3000`. For panel embedding, ensure Grafana allows embedding (adjust `grafana.ini` allow_embedding = true) and secure access (API token or reverse proxy with auth).

---

## Security & hardening

* Use HTTPS (Caddy handles TLS automatically for domain; for Tailscale-only, consider using mTLS or Tailscale ACLs).
* Never expose Docker socket to untrusted services without strong auth.
* Store `SECRET_KEY` and `ROOT_PASSWORD` in environment variables or Docker secrets.
* Rate limit `/api/auth` endpoints.
* Validate and sanitize any shell commands; prefer allow-listed commands or wrapper scripts.
* Limit file upload size per request and check content-type.
* Run backend with a non-root user inside the container.

---

## Deployment steps (practical)

1. On your dev machine: create repo structure and implement backend + frontend.
2. Build and test locally with `docker compose up --build`.
3. Prepare server:

   * Install Docker & Docker Compose.
   * Place repo in `/opt/server-portal` (or `/srv/server-portal`).
   * Ensure `/opt/server-portal/data` (or mapped `portal_data`) has correct permissions.
4. Copy `docker-compose.yml` and `caddy/Caddyfile` to server.
5. Set secrets as environment variables in a `.env` file (not committed).
6. `docker compose up -d` on server.
7. Seed `root` account if not created automatically.
8. Configure Grafana to scrape `http://backend:8000/metrics` (or host mapping) and import dashboards.

---

## Example quick commands (on server)

```bash
# clone
sudo mkdir -p /opt/server-portal
sudo chown $USER:$USER /opt/server-portal
cd /opt/server-portal
git clone <repo> .

# set env
cat > .env <<EOF
SECRET_KEY=verysecret
ROOT_PASSWORD=ChangeMeNow!
EOF

# start
docker compose up -d --build

# check logs
docker compose logs -f backend
```

---

## Notes, trade-offs and next steps

* **SQLite** is simple but limited under concurrency; fine for low user counts. Migrate to Postgres for production.
* **Application-level quotas** are easiest to implement quickly. If you expect heavy storage usage or multi-tenant performance, move to filesystem quotas or a dedicated object store.
* **Minecraft management** via Docker is safest; controlling host processes from a container is more complex security-wise.
* **Backups:** schedule `rsync` or `duplicity` snapshots for `/data` and `portal.db` (weekly/daily depending on needs).

---

## Admin checklist before first deploy

* [ ] Generate a strong `SECRET_KEY` and set in `.env`.
* [ ] Replace seeded root password immediately.
* [ ] Ensure `/data/storage` exists and is writable by the backend container.
* [ ] Decide whether Minecraft is containerized or host-managed; create systemd unit if host-managed.
* [ ] Configure Grafana datasource and dashboards to point at backend metrics.

Server names:
* Aurora-Ymir-1
*Aurora-Ymir-2
*Aurora-Frostbyte-(AF1)
*Aurora-Frostbyte-(AF2)

Mer namn som kan komma att användas:
Nordiskt/aurora-tema (perfekt för ditt brand)

aurora-zenith-1 (AZ-1)

aurora-hyperion-1 (AH-1)


⚡ Mer “datacenter/energi”-känsla

AUR-NOVA-

AUR-PULSE-

AUR-QUASAR-

AUR-LUMIN-

AUR-ION-

🌌 Mer atmosfäriskt/himmelsinspirerat

aurora-stratos-

aurora-celest-

aurora-halo-

aurora-solstice-

aurora-eclipse-

🧊 Extra nordisk/mytologi-touch
aurora-mimir-

aurora-fenrir-

aurora-jotun-

aurora-odin-

---
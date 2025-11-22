🌌 Aurora Server Portal

Aurora is a futuristic, self-hosted server dashboard designed to manage a Linux-based home server. Featuring a Cyberpunk-inspired UI, it provides real-time system telemetry, Minecraft server management, file storage, and an integrated AI assistant powered by AWS Bedrock.

✨ Features

🖥️ NeuralNet Dashboard: A unified hub for weather, calendars, and quick system actions.

📊 Live Telemetry: Real-time monitoring of CPU, RAM, Disk usage, and Network traffic using psutil.

⛏️ Minecraft Control: Start, stop, restart, and monitor your Minecraft server via a web-based terminal (RCON/Screen wrapper).

🤖 Borealis AI: Integrated AI assistant (Claude 3 via AWS Bedrock) with context-awareness of server health.

📂 Storage Manager: Browse, upload, and manage files on the server.

🔒 Secure Access: JWT-based authentication protecting all API endpoints.

🛠️ Tech Stack

Frontend (Client-Side)

Architecture: No-Build Single Page Application (SPA).

Framework: React 18 (loaded via ESM/Import Maps).

Styling: Tailwind CSS (via CDN).

Icons: Lucide React.

Note: The frontend runs directly in the browser without Node.js or Webpack build steps, served statically by Nginx.

Backend (Server-Side)

Framework: Python FastAPI.

Server: Uvicorn (ASGI).

Database: SQLite (via SQLAlchemy).

System Interaction: psutil for metrics, subprocess for Minecraft control.

AI: boto3 SDK for AWS Bedrock integration.

Infrastructure

OS: Ubuntu Linux.

Web Server: Nginx (Reverse Proxy & Static File Serving).

Process Manager: Systemd (keeps the backend alive).

🚀 Deployment & CI/CD

This project uses GitHub Actions for continuous deployment.

Workflow

Code is pushed to the main branch.

GitHub Actions triggers the deploy pipeline.

The runner connects to the production server via SSH.

The repo is pulled/synced to the server.

Backend dependencies are updated (pip install).

Frontend files (index.html) are copied to the Nginx web root (/var/www/aurora).

The systemd service (aurora.service) is restarted.

Setup Requirements

To replicate this deployment, add the following Repository Secrets in GitHub:

HOST: Your server's IP address.

USERNAME: The SSH user (e.g., aurora).

SSH_PRIVATE_KEY: Your private SSH key authorized on the server.

⚙️ Configuration

Environment Variables

The backend requires a .env file located in backend/app/. Do not commit this file.

# Security
SECRET_KEY=your_super_secret_jwt_key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=60

# Initial Admin Setup
ROOT_PASSWORD=change_me_immediately

# AWS Bedrock (AI)
AWS_ACCESS_KEY_ID=your_aws_key
AWS_SECRET_ACCESS_KEY=your_aws_secret
BEDROCK_REGION=us-east-1


Nginx Configuration

Nginx is configured to serve the static frontend and proxy API requests to Uvicorn running on port 8590.

server {
    listen 80;
    root /var/www/aurora;
    index index.html;

    location /api/ {
        proxy_pass [http://127.0.0.1:8590](http://127.0.0.1:8590);
        # ... proxy headers ...
    }
}


📦 Local Development

Clone the repo:

git clone [https://github.com/yourusername/aurora-server.git](https://github.com/yourusername/aurora-server.git)


Setup Backend:

cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8590


Setup Frontend:
Since there is no build step, simply open frontend/index.html in a browser (or serve it with a simple HTTP server like Live Server). Note: You will need to proxy API calls to localhost:8590 manually or disable CORS during local dev.

📜 License

Private Project. All rights reserved. Mallard-Dash
[
  {
    "name": "alpine",
    "image": "alpine:latest",
    "command": "tail -f /dev/null",
    "ports": []
  },
  {
    "name": "nginx",
    "image": "nginx:latest",
    "command": null,
    "ports": [80]
  },
  {
    "name": "redis",
    "image": "redis:alpine",
    "command": null,
    "ports": [6379]
  },
  {
    "name": "python-web",
    "image": "python:3.9-slim",
    "command": "python3 -m http.server 8000",
    "ports": [8000]
  }
]
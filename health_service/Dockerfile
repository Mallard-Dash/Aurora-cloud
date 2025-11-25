# Använd en lättviktig Python-version
FROM python:3.9-slim

# Sätt arbetskatalogen
WORKDIR /app

# Kopiera requirements och installera
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiera själva applikationen
COPY aurora_health_service.py .

# Exponera porten
EXPOSE 8050

# Starta appen
CMD ["python", "aurora_health_service.py"]
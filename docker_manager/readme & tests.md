Aurora Docker Manager Backend

Run Locally

pip install -r requirements.txt

uvicorn app.main:app --reload

Run with Docker Compose

docker-compose up --build -d

API available at http://localhost:8001

Smoke Tests (Curl)

Run these commands to verify functionality.

Login:

TOKEN=$(curl -s -X POST "http://localhost:8001/api/login" -H "Content-Type: application/json" -d '{"username":"admin", "password":"admin"}' | jq -r .access_token)
echo "Token: $TOKEN"


List Containers:

curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/containers | jq .


Create Container (nginx):

curl -s -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"name":"test-nginx", "template":"nginx"}' http://localhost:8001/api/containers/create


Stop Container:

# Replace ID with actual ID from list
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/containers/test-nginx/stop


Start Container:

curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/containers/test-nginx/start


Delete Container:

curl -s -X DELETE -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/containers/test-nginx

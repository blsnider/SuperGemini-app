FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# Single worker: the sniper holds in-process timing state during the release
# window and Cloud Run is pinned to 1 instance (§1).
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 360 app:app

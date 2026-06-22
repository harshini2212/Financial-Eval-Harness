# Full tieout app (live agent + benchmark) for Render / Railway / Fly / any Docker host.
FROM python:3.11-slim

WORKDIR /app

# Native libs in case lxml/arelle need to build from source (wheels usually cover it).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The host injects $PORT; serve.py reads it and binds 0.0.0.0 when PORT is set.
ENV PORT=8000
EXPOSE 8000
CMD ["python", "serve.py"]

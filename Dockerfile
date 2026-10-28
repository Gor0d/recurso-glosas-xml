FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts ./scripts
COPY web ./web
COPY xsd ./xsd
COPY resources ./resources
COPY output ./output

RUN useradd --create-home --uid 10001 nexo \
    && chown -R nexo:nexo /app

USER nexo
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)" || exit 1

CMD ["python", "scripts/analyst_panel.py", "--host", "0.0.0.0", "--port", "8765", "--allow-network"]

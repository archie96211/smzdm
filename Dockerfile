FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 PORT=18080 TZ=Asia/Shanghai \
    SMZDM_DATA_DIR=/data SMZDM_LOG_DIR=/tmp/logs \
    SMZDM_LOG_STDOUT_ONLY=true SMZDM_WECHAT_BRIDGE_ENABLED=false
WORKDIR /app
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt && \
    groupadd --gid 10001 smzdm && useradd --uid 10001 --gid smzdm --no-create-home smzdm && \
    mkdir /data && chown smzdm:smzdm /data
COPY src ./src
COPY static ./static
COPY start.py .
USER smzdm
EXPOSE 18080
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:18080/api/health',timeout=3)"
CMD ["python", "start.py"]

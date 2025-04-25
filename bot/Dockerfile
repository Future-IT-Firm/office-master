FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies and PowerShell for ARM64
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       wget \
       ca-certificates \
       libicu-dev \
    && wget https://github.com/PowerShell/PowerShell/releases/download/v7.5.1/powershell-7.5.1-linux-arm64.tar.gz && mkdir -p /opt/microsoft/powershell/7 && tar -xzf powershell-7.5.1-linux-arm64.tar.gz -C /opt/microsoft/powershell/7 && ln -s /opt/microsoft/powershell/7/pwsh /usr/bin/pwsh && chmod 777  /usr/bin/pwsh

WORKDIR /app

# Install Python dependencies
RUN pip3 install --no-cache-dir httpx msal aiogram

# Copy application code
COPY . .

# Prepare entrypoint and data dirs
RUN chmod +x entrypoint.sh \
    && mkdir -p /data /shared/storage

ENTRYPOINT ["./entrypoint.sh"]

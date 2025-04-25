FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        apt-transport-https \
        ca-certificates \
        gnupg && \
    wget -q https://github.com/PowerShell/PowerShell/releases/download/v7.5.1/powershell_7.5.1-1.deb_amd64.deb && \
    dpkg -i powershell_7.5.1-1.deb_amd64.deb || true && \
    apt-get install -f -y && \
    rm powershell_7.5.1-1.deb_amd64.deb && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip3 install httpx msal aiogram

COPY . .

RUN chmod +x entrypoint.sh \
 && mkdir -p /data /shared/storage

ENTRYPOINT ["./entrypoint.sh"]

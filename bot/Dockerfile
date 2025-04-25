FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN wget https://github.com/PowerShell/PowerShell/releases/download/v7.5.1/powershell_7.5.1-1.deb_amd64.deb && dpkg -i powershell_7.5.1-1.deb_amd64.deb || apt-get install -f -y

WORKDIR /app

RUN pip3 install httpx msal aiogram

COPY . .

RUN chmod +x entrypoint.sh \
 && mkdir -p /data /shared/storage

ENTRYPOINT ["./entrypoint.sh"]

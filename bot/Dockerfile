FROM mcr.microsoft.com/dotnet/sdk:8.0 AS base

ENV POWERSHELL_TELEMETRY_OPTOUT=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip curl \
    && ln -sf /usr/bin/python3 /usr/bin/python \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
RUN pip3 install httpx msal aiogram --break-system-packages

COPY . .

RUN chmod +x entrypoint.sh \
    && mkdir -p /data /shared/storage

ENTRYPOINT ["./entrypoint.sh"]

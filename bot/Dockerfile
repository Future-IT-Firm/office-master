FROM python:3.11-slim

# don’t buffer Python stdout/stderr, don’t write .pyc files
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# set your working dir
WORKDIR /app
RUN pip3 install httpx msal aiogram

# 2) now copy the rest of your app
COPY . .

# 3) make your entrypoint executable & prepare data dirs
RUN chmod +x entrypoint.sh \
 && mkdir -p /data /shared/storage

# 4) run
ENTRYPOINT ["./entrypoint.sh"]

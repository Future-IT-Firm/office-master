import asyncio
import logging
from pathlib import Path
import httpx
import msal

API_BASE_URL = 'https://graph.microsoft.com/v1.0'
logging.basicConfig(level=logging.INFO)

async def get_access_token(client_id: str, tenant_id: str, client_secret: str) -> str | None:
    loop = asyncio.get_running_loop()
    def fetch_token():
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=authority,
            client_credential=client_secret
        )
        token_response = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        # Extract and return the access token string, or None if not present
        return token_response.get("access_token") if token_response else None
    try:
        token = await loop.run_in_executor(None, fetch_token)
        if not token:
            logging.error("Token fetch returned no access_token")
        return token
    except Exception as e:
        logging.error(f"Error acquiring token: {e}")
        return None

async def create_user(access_token: str, email: str, ms_acc_domain: str, session: httpx.AsyncClient) -> bool | None:
    display_name = email.split('@')[0].replace('.', ' ').title()
    principal_name = f"{email.replace('@', '_')}#EXT#@{ms_acc_domain}"
    payload = {
        "accountEnabled": True,
        "displayName": display_name,
        "mailNickname": email.split('@')[0],
        "userPrincipalName": principal_name,
        "userType": "Guest",
        "mail": email,
        "passwordProfile": {
            "forceChangePasswordNextSignIn": True,
            "password": "Welcome@123"
        }
    }
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    try:
        resp = await session.post(f"{API_BASE_URL}/users", headers=headers, json=payload)
        if resp.status_code == 201:
            logging.info(f"Created {email}")
            return True
        text = await resp.text()
        if 'Directory_QuotaExceeded' in text:
            logging.warning(f"Quota exceeded for {email}")
            return False
        logging.error(f"Failed {email}: {resp.status_code} {text}")
        return None
    except Exception as e:
        logging.error(f"Exception creating {email}: {e}")
        return None

async def process_user_creation(record: str, storage_dir: Path, workers_per_account: int, session: httpx.AsyncClient):
    fields = record.split('\t')
    account_email, client_secret, client_id, tenant_id = fields[0], fields[3], fields[4], fields[5]
    domain = account_email.split('@')[1]
    file = storage_dir / f"{account_email}.txt"
    if not file.exists():
        logging.error(f"Missing file {file}")
        return
    emails = file.read_text().splitlines()
    token = await get_access_token(client_id, tenant_id, client_secret)
    if not token:
        Path('failed.txt').write_text(f"{account_email}\n", append=True)
        return
    total = 0
    sem = asyncio.Semaphore(workers_per_account)
    async def sem_create(e):
        async with sem:
            res = await create_user(token, e, domain, session)
            return res
    tasks = [sem_create(e) for e in emails]
    for coro in asyncio.as_completed(tasks):
        res = await coro
        if res is True:
            total += 1
        elif res is False:
            break
    Path('success.txt').write_text(f"{account_email} - {total}\n", append=True)
    logging.info(f"{account_email} done: {total}")

async def run_uploader(data_file: Path, storage_dir: Path, workers_per_account: int, batch_size: int):
    storage_dir.mkdir(parents=True, exist_ok=True)
    records = data_file.read_text().splitlines()
    async with httpx.AsyncClient(timeout=25) as session:
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            await asyncio.gather(*(process_user_creation(r, storage_dir, workers_per_account, session) for r in batch))
    logging.info("All uploads completed")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-file', type=Path, default=Path('data.txt'))
    parser.add_argument('--storage-dir', type=Path, default=Path('storage'))
    parser.add_argument('--workers-per-account', type=int, default=10)
    parser.add_argument('--batch-size', type=int, default=5)
    args = parser.parse_args()
    asyncio.run(run_uploader(args.data_file, args.storage_dir, args.workers_per_account, args.batch_size))

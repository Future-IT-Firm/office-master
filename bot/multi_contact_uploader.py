import asyncio
import logging
from pathlib import Path
import httpx
import msal

API_BASE_URL = 'https://graph.microsoft.com/v1.0'
logging.basicConfig(level=logging.INFO)

async def get_access_token(client_id: str, tenant_id: str, client_secret: str) -> str | None:
    """
    Obtain an OAuth2 access token for Microsoft Graph using client credentials.
    """
    loop = asyncio.get_running_loop()
    def fetch_token():
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            authority=authority,
            client_credential=client_secret
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
        return result.get("access_token") if isinstance(result, dict) else None
    try:
        token = await loop.run_in_executor(None, fetch_token)
        if not token:
            logging.error("Token fetch returned no access_token")
        return token
    except Exception as e:
        logging.error(f"Error acquiring token: {e}")
        return None

async def create_user(access_token: str, email: str, domain: str, session: httpx.AsyncClient) -> bool | None:
    """
    Create a guest user in Azure AD for the given email.
    Returns True on success, False on quota exceeded, None on other errors.
    """
    display_name = email.split('@')[0].replace('.', ' ').title()
    principal_name = f"{email.replace('@', '_')}#EXT#@{domain}"
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
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    try:
        resp = await session.post(f"{API_BASE_URL}/users", headers=headers, json=payload)
        if resp.status_code == 201:
            logging.info(f"Created {email}")
            return True
        # read .text property; do not call it
        body = resp.text
        if 'Directory_QuotaExceeded' in body:
            logging.warning(f"Quota exceeded for {email}")
            return False
        logging.error(f"Failed {email}: {resp.status_code} {body}")
        return None
    except Exception as e:
        logging.error(f"Exception creating {email}: {e}")
        return None

async def process_user_creation(record: str, storage_dir: Path, workers: int, session: httpx.AsyncClient):
    """
    Process a single account record: read its .txt file, acquire token, create users in parallel.
    """
    fields = record.split('\t')
    account_email = fields[0]
    client_secret = fields[3]
    client_id = fields[4]
    tenant_id = fields[5]
    domain = account_email.split('@')[1]

    file_path = storage_dir / f"{account_email}.txt"
    if not file_path.exists():
        logging.error(f"Missing file for {account_email}")
        return
    emails = file_path.read_text().splitlines()

    token = await get_access_token(client_id, tenant_id, client_secret)
    if not token:
        with open('failed.txt', 'a', encoding='utf-8') as f:
            f.write(f"{account_email}\n")
        return

    sem = asyncio.Semaphore(workers)
    async def worker_task(email: str):
        async with sem:
            return await create_user(token, email, domain, session)

    total_created = 0
    tasks = [worker_task(e) for e in emails]
    for coro in asyncio.as_completed(tasks):
        result = await coro
        if result is True:
            total_created += 1
        elif result is False:
            # stop on quota exceeded
            break

    with open('success.txt', 'a', encoding='utf-8') as f:
        f.write(f"{account_email} - {total_created}\n")
    logging.info(f"{account_email}: created {total_created} users")

async def run_uploader(data_file: Path, storage_dir: Path, workers_per_account: int, batch_size: int):
    storage_dir.mkdir(exist_ok=True, parents=True)
    records = data_file.read_text().splitlines()

    async with httpx.AsyncClient(timeout=25) as session:
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
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

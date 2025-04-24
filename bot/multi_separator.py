import asyncio
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)

def separate_data_for_user(user: str, main_file: Path, cut_size: int, storage_dir: Path):
    lines = main_file.read_text().splitlines()
    chunk, remainder = lines[:cut_size], lines[cut_size:]
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / f"{user}.txt").write_text("\n".join(chunk) + "\n")
    main_file.write_text("\n".join(remainder) + ("\n" if remainder else ""))
    logging.info(f"Separated {cut_size} emails for {user}, {len(remainder)} left in main list")

async def run_separator(users_file: Path, main_file: Path, cut_size: int, storage_dir: Path):
    users = users_file.read_text().splitlines()
    total = len(main_file.read_text().splitlines())
    needed = cut_size * len(users)
    if needed > total:
        logging.warning(f"Insufficient emails: need {needed}, have {total}")
        return
    loop = asyncio.get_running_loop()
    tasks = []
    for user in users:
        tasks.append(loop.run_in_executor(None, separate_data_for_user, user, main_file, cut_size, storage_dir))
    await asyncio.gather(*tasks)
    logging.info("All user chunks created")

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--users-file', type=Path, default=Path('users.txt'))
    parser.add_argument('--main-file', type=Path, default=Path('all_data.txt'))
    parser.add_argument('--cut-size', type=int, required=True)
    parser.add_argument('--storage-dir', type=Path, default=Path('storage'))
    args = parser.parse_args()
    asyncio.run(run_separator(args.users_file, args.main_file, args.cut_size, args.storage_dir))

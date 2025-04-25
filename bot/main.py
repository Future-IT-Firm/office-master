#!/usr/bin/env python3
import os
import asyncio
import logging
import re
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from multi_separator import run_separator
from multi_contact_uploader import run_uploader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

BOT_TOKEN         = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN required")
CUT_SIZE          = int(os.getenv("CUT_SIZE", "0"))
BATCH_SIZE        = int(os.getenv("BATCH_SIZE", "0"))
WORKERS_PER_ACCOUNT = int(os.getenv("WORKERS_PER_ACCOUNT", "0"))

ADMIN_IDS   = set(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(","))))
GENERAL_IDS = set(map(int, filter(None, os.getenv("GENERAL_IDS", "").split(","))))

DATA_ROOT   = Path("/data")
ADMIN_ROOT  = Path("/shared")
MASTER_FILE = ADMIN_ROOT / "all_data.txt"
STORAGE_ROOT = ADMIN_ROOT / "storage"

SCRIPT_DIR  = Path(__file__).parent.resolve()
PS_SCRIPT   = SCRIPT_DIR / "create_group.ps1"
PS_LOG_FILE = SCRIPT_DIR / "creation_log.txt"

for d in (DATA_ROOT, ADMIN_ROOT, STORAGE_ROOT):
    d.mkdir(parents=True, exist_ok=True)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(bot=bot, storage=MemoryStorage())
task_queue: asyncio.Queue[int] = asyncio.Queue()

class UploadStates(StatesGroup):
    waiting_for_data = State()
    waiting_for_master = State()

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

def is_general(uid: int) -> bool:
    return uid in GENERAL_IDS

async def notify_admins(sender: int, text: str):
    for uid in ADMIN_IDS - {sender}:
        await bot.send_message(uid, text)

@dp.message(Command("start"))
async def cmd_start(m: Message):
    await m.answer(
        "👋 Welcome!\n"
        "`/upload_data` → send your `data.txt`\n"
        "`/run` → process current batch\n"
    )

@dp.message(Command("upload_data"))
async def cmd_upload_data(m: Message, state: FSMContext):
    if not (is_admin(m.from_user.id) or is_general(m.from_user.id)):
        return await m.answer("🚫 Unauthorized")
    await state.set_state(UploadStates.waiting_for_data)
    await m.answer("📂 Please send your `data.txt` file.")

@dp.message(UploadStates.waiting_for_data, F.document)
async def handle_data_upload(m: Message, state: FSMContext):
    dest = DATA_ROOT / "data.txt"
    await bot.download(m.document, dest)
    await m.answer("✅ `data.txt` saved.")
    await state.clear()

@dp.message(Command("upload_main"))
async def cmd_upload_main(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return await m.answer("🚫 Unauthorized")
    await state.set_state(UploadStates.waiting_for_master)
    await m.answer("📂 Please send the `all_data.txt` master list.")

@dp.message(UploadStates.waiting_for_master, F.document)
async def handle_master_upload(m: Message, state: FSMContext):
    await bot.download(m.document, MASTER_FILE)
    await m.answer("✅ Master list saved.")
    await notify_admins(m.from_user.id, "🔄 `all_data.txt` has been updated.")
    await state.clear()

@dp.message(Command("run"))
async def cmd_run(m: Message):
    uid = m.from_user.id
    if not (is_admin(uid) or is_general(uid)):
        return await m.answer("🚫 Unauthorized")
    if not MASTER_FILE.exists():
        return await m.answer("❗ Master list (`all_data.txt`) missing.")
    if CUT_SIZE <= 0 or BATCH_SIZE <= 0 or WORKERS_PER_ACCOUNT <= 0:
        return await m.answer("❗ Configuration missing or invalid.")
    if not (DATA_ROOT / "data.txt").exists():
        return await m.answer("❗ `data.txt` not found.")
    await m.answer("🔄 Job queued.")
    await task_queue.put(uid)

async def worker():
    while True:
        uid = await task_queue.get()
        try:
            data_file  = DATA_ROOT / "data.txt"
            lines      = data_file.read_text(encoding="utf-8").splitlines()
            users, groups = [], []
            valid_records = []

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                parts = re.split(r"\s+", stripped)
                if len(parts) < 6:
                    logging.warning("Skipping malformed line: %r", line)
                    continue
                email, pwd = parts[0], parts[1]
                users.append(email)
                groups.append(f"{email}\t{pwd}")
                valid_records.append("\t".join(parts))
            users_txt = DATA_ROOT / "users.txt"
            group_txt = DATA_ROOT / "group.txt"
            users_txt.write_text("\n".join(users) + "\n", encoding="utf-8")
            group_txt.write_text("\n".join(groups) + "\n", encoding="utf-8")
            (SCRIPT_DIR / "users.txt").write_text("\n".join(users) + "\n", encoding="utf-8")
            (SCRIPT_DIR / "group.txt").write_text("\n".join(groups) + "\n", encoding="utf-8")
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pwsh", "-File", str(PS_SCRIPT),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(SCRIPT_DIR),
                )
                out, err = await proc.communicate()
                exit_code = proc.returncode
                out_txt = out.decode(errors="ignore").strip()
                err_txt = err.decode(errors="ignore").strip()
                combined = "\n".join(filter(None, [out_txt, err_txt]))

                if exit_code == 0:
                    if PS_LOG_FILE.exists():
                        log_txt = PS_LOG_FILE.read_text(encoding="utf-8")
                        await bot.send_message(uid, f"📋 PowerShell log:\n{log_txt}")
                    else:
                        await bot.send_message(uid, f"✅ PS succeeded:\n{combined or '<no output>'}")
                else:
                    await bot.send_message(
                        uid,
                        f"❌ PS failed (exit {exit_code}):\n{combined or '<no output>'}"
                    )
            except FileNotFoundError:
                await bot.send_message(uid, "❌ `pwsh` not found; skipped group creation.")
            except Exception as ps_exc:
                logging.exception("PowerShell script error")
                await bot.send_message(uid, f"⚠️ PS exception:\n{ps_exc}")

            await bot.send_message(uid, "📤 Running separator...")
            await run_separator(users_txt, MASTER_FILE, CUT_SIZE, STORAGE_ROOT)

            valid_file = DATA_ROOT / "data_valid.txt"
            valid_file.write_text("\n".join(valid_records) + "\n", encoding="utf-8")

            await bot.send_message(uid, "☁️ Running uploader...")
            try:
                await run_uploader(valid_file, STORAGE_ROOT, WORKERS_PER_ACCOUNT, BATCH_SIZE)
            except Exception as up_err:
                logging.exception("Uploader error")
                await bot.send_message(uid, f"⚠️ Uploader exception:\n{up_err}")
            success_file = Path("success.txt")
            fail_file    = Path("failed.txt")
            success_file.touch(exist_ok=True)
            fail_file.touch(exist_ok=True)

            succ_txt = success_file.read_text(encoding="utf-8").strip() or "(no successes)"
            fail_txt = fail_file.read_text(encoding="utf-8").strip()    or "(no failures)"
            await bot.send_message(
                uid,
                f"✅ Successes:\n{succ_txt}\n\n❌ Failures:\n{fail_txt}"
            )

        except Exception as e:
            logging.exception("Worker loop error")
            await bot.send_message(uid, f"⚠️ Worker error:\n{e}")
        finally:
            task_queue.task_done()

async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    for _ in range(2):
        asyncio.create_task(worker())

if __name__ == "__main__":
    dp.startup.register(on_startup)
    asyncio.run(dp.start_polling(bot, skip_updates=True))

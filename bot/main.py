import os
import asyncio
import logging
from pathlib import Path
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from multi_separator import run_separator
from multi_contact_uploader import run_uploader

logging.basicConfig(level=logging.INFO)
BOT_TOKEN = os.getenv('BOT_TOKEN') or exit("BOT_TOKEN required")
CUT_SIZE = int(os.getenv('CUT_SIZE', '0'))
BATCH_SIZE = int(os.getenv('BATCH_SIZE', '0'))
WORKERS_PER_ACCOUNT = int(os.getenv('WORKERS_PER_ACCOUNT', '0'))
ADMIN_IDS = set(map(int, filter(None, os.getenv('ADMIN_IDS', '').split(','))))
GENERAL_IDS = set(map(int, filter(None, os.getenv('GENERAL_IDS', '').split(','))))

DATA_ROOT = Path('/data')
ADMIN_ROOT = Path('/shared')
MASTER_FILE = ADMIN_ROOT / 'all_data.txt'
STORAGE_ROOT = ADMIN_ROOT / 'storage'
PS_SCRIPT = ADMIN_ROOT / 'create_group.ps1'
LOG_FILE = ADMIN_ROOT / 'creation_log.txt'

for p in (DATA_ROOT, ADMIN_ROOT, STORAGE_ROOT):
    p.mkdir(exist_ok=True, parents=True)

task_queue: asyncio.Queue[int] = asyncio.Queue()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot=bot, storage=MemoryStorage())

class UploadStates(StatesGroup):
    data = State()
    main = State()

def is_admin(u):
    return u in ADMIN_IDS

def is_general(u):
    return u in GENERAL_IDS

async def notify_admins(sender, text):
    for a in ADMIN_IDS - {sender}:
        await bot.send_message(a, text)

@dp.message(Command('start'))
async def start_cmd(m: Message):
    await m.answer(
        "Welcome!\n"
        "Use /upload_data to upload your data.txt file.\n"
        "Use /run to start processing.\n"
    )

@dp.message(Command('upload_data'))
async def upload_data(m: Message, state: FSMContext):
    if not (is_admin(m.from_user.id) or is_general(m.from_user.id)):
        return await m.answer('Unauthorized')
    await state.set_state(UploadStates.data)
    await m.answer('Send data.txt')

@dp.message(UploadStates.data, F.document)
async def receive_data(m: Message, state: FSMContext):
    dest = DATA_ROOT / 'data.txt'
    await bot.download(m.document, dest)
    await m.answer('data.txt saved')
    await state.clear()

@dp.message(Command('upload_main'))
async def upload_main(m: Message, state: FSMContext):
    if not is_admin(m.from_user.id):
        return await m.answer('Unauthorized')
    await state.set_state(UploadStates.main)
    await m.answer('Send all_data.txt')

@dp.message(UploadStates.main, F.document)
async def receive_main(m: Message, state: FSMContext):
    await bot.download(m.document, MASTER_FILE)
    await m.answer('Master list saved')
    await notify_admins(m.from_user.id, 'Master list updated')
    await state.clear()

@dp.message(Command('run'))
async def run_cmd(m: Message):
    if not (is_admin(m.from_user.id) or is_general(m.from_user.id)):
        return await m.answer('Unauthorized')
    if not MASTER_FILE.exists():
        return await m.answer('No master list')
    if not (CUT_SIZE and BATCH_SIZE and WORKERS_PER_ACCOUNT):
        return await m.answer('Config missing')
    if not (DATA_ROOT / 'data.txt').exists():
        return await m.answer('No data.txt')
    await m.answer('Queued')
    await task_queue.put(m.from_user.id)

async def worker():
    while True:
        uid = await task_queue.get()
        try:
                proc = await asyncio.create_subprocess_exec(
                    'sh -c /usr/bin/pwsh', '-File', str(PS_SCRIPT), 
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                )
        except FileNotFoundError:
            await bot.send_message(uid, "❌ PowerShell executable not found.")
            task_queue.task_done()
            continue
            out, err = await proc.communicate()
            if LOG_FILE.exists():
                txt = LOG_FILE.read_text()
                await bot.send_message(uid, f"📋 Group creation log:\n{txt}")
            else:
                await bot.send_message(uid, f"Group script error:\n{err.decode()}")

            await bot.send_message(uid, 'Running separator...')
            await run_separator(DATA_ROOT / 'users.txt', MASTER_FILE, CUT_SIZE, STORAGE_ROOT)
            await bot.send_message(uid, 'Running uploader...')
            await run_uploader(DATA_ROOT / 'data.txt', STORAGE_ROOT, WORKERS_PER_ACCOUNT, BATCH_SIZE)

            success = Path('success.txt')
            fail = Path('failed.txt')
            s = success.read_text().strip() if success.exists() else '(no successes)'
            f = fail.read_text().strip() if fail.exists() else '(no failures)'
            await bot.send_message(uid, f"✅ Successes:\n{s}\n\n❌ Failures:\n{f}")
        except Exception as e:
            logging.error(e)
            await bot.send_message(uid, f'Error: {e}')
        finally:
            task_queue.task_done()

async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    for _ in range(2):
        asyncio.create_task(worker())

if __name__ == '__main__':
    dp.startup.register(on_startup)
    asyncio.run(dp.start_polling(bot))

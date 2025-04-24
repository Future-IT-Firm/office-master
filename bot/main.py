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

data_root = Path('/data')
admin_root = Path('/shared')
master_file = admin_root / 'all_data.txt'
storage_root = admin_root / 'storage'

for p in (data_root, admin_root, storage_root):
    p.mkdir(exist_ok=True, parents=True)

task_queue: asyncio.Queue[int] = asyncio.Queue()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot=bot, storage=MemoryStorage())

class UploadStates(StatesGroup):
    data = State()
    main = State()

def is_admin(u): return u in ADMIN_IDS
def is_general(u): return u in GENERAL_IDS

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
    dest = data_root / 'data.txt'
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
    await bot.download(m.document, master_file)
    await m.answer('Master list saved')
    await notify_admins(m.from_user.id, 'Master list updated')
    await state.clear()

@dp.message(Command('run'))
async def run_cmd(m: Message):
    if not (is_admin(m.from_user.id) or is_general(m.from_user.id)):
        return await m.answer('Unauthorized')
    if not master_file.exists():
        return await m.answer('No master list')
    if not (CUT_SIZE and BATCH_SIZE and WORKERS_PER_ACCOUNT):
        return await m.answer('Config missing')
    if not (data_root / 'data.txt').exists():
        return await m.answer('No data.txt')
    await m.answer('Queued')
    await task_queue.put(m.from_user.id)

async def worker():
    while True:
        uid = await task_queue.get()
        try:
            out_dir = storage_root
            out_dir.mkdir(exist_ok=True, parents=True)

            lines = (data_root / 'data.txt').read_text().splitlines()
            users = [l.split('\t',1)[0] for l in lines if l.strip()]
            uf = data_root / 'users.txt'
            uf.write_text('\n'.join(users) + '\n')
            await bot.send_message(uid, f'Users: {len(users)}')

            await bot.send_message(uid, 'Running separator...')
            await run_separator(Path(uf), master_file, CUT_SIZE, out_dir)

            await bot.send_message(uid, 'Running uploader...')
            await run_uploader(data_root / 'data.txt', out_dir, WORKERS_PER_ACCOUNT, BATCH_SIZE)


            success_path = Path('success.txt')
            failed_path  = Path('failed.txt')

            success_text = success_path.read_text().strip() if success_path.exists() else "(no successes)"
            failed_text  = failed_path.read_text().strip()  if failed_path.exists()  else "(no failures)"

            report = (
                f"✅ Successes:\n{success_text}\n\n"
                f"❌ Failures:\n{failed_text}"
            )
            await bot.send_message(uid, report)

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

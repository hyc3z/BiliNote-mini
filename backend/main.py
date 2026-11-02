import os
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1]/'.env')
load_dotenv()

import uvicorn
from starlette.middleware.cors import CORSMiddleware
from app import create_app
from app.db.init_db import init_db
from app.db.provider_dao import seed_default_providers
from app.services.recover_tasks import recover_interrupted_tasks
from app.services.library import migrate
from app.services.proxy_config_manager import ProxyConfigManager
from app.exceptions.exception_handlers import register_exception_handlers

@asynccontextmanager
async def lifespan(app):
    init_db()
    seed_default_providers()
    folder=os.getenv('NOTE_OUTPUT_DIR','note_results')
    recover_interrupted_tasks(folder)
    migrate(folder)
    ProxyConfigManager().apply_to_env()
    yield

app=create_app(lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origin_regex=r'^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$',allow_methods=['*'],allow_headers=['*'])
register_exception_handlers(app)

if __name__=='__main__':
    uvicorn.run(app,host=os.getenv('BACKEND_HOST','127.0.0.1'),port=int(os.getenv('BACKEND_PORT','8483')))

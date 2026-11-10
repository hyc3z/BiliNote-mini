from fastapi import FastAPI

from .routers import note, provider, model, config, comments



def create_app(lifespan) -> FastAPI:
    app = FastAPI(title="BiliNote",lifespan=lifespan)
    app.include_router(note.router, prefix="/api")
    app.include_router(provider.router, prefix="/api")
    app.include_router(model.router,prefix="/api")
    app.include_router(config.router,  prefix="/api")
    app.include_router(comments.router,prefix="/api")
    # Mini does not load the vector search / chat subsystem.

    from pathlib import Path
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse
    ui=Path(__file__).resolve().parents[2]/'BillNote_frontend/dist'
    if (ui/'index.html').is_file():
        app.mount('/assets',StaticFiles(directory=ui/'assets'),name='workbench-assets')
        @app.get('/',include_in_schema=False)
        @app.get('/settings',include_in_schema=False)
        @app.get('/settings/{rest:path}',include_in_schema=False)
        def workbench(rest:str=''):
            return FileResponse(ui/'index.html')
    return app

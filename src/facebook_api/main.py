from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from facebook_api.config import settings
from facebook_api.database import init_db
from facebook_api.routers import auth, groups, posts
from facebook_api.utils.browser import browser_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await browser_manager.start()
    yield
    await browser_manager.stop()


app = FastAPI(
    title=settings.APP_NAME,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(groups.router)
app.include_router(posts.router)


@app.get("/")
async def root():
    return {"message": "Facebook API is running"}

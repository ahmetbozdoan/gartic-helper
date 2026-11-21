"""FastAPI uygulama giriş noktası: `rye run dev`"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from gartic_helper.config import get_settings
from gartic_helper.controllers import guess_controller, guide_controller, words_controller
from gartic_helper.dependencies import (
    get_clip_word_ranker,
    get_quickdraw_classifier,
    get_word_matcher,
)
from gartic_helper.utils.logging_utils import setup_logging


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # CLIP'in yüklenmesi tahmin isteğinin zaman aşımından uzun sürebildiği için açılışta başlatılır.
    get_clip_word_ranker().start_loading(get_word_matcher().words)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(title="Gartic Helper API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=settings.allowed_origin_regex,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(guess_controller.router)
    app.include_router(guide_controller.router)
    app.include_router(words_controller.router)

    @app.get("/health")
    async def health() -> dict[str, bool | str]:
        return {
            "status": "ok",
            "classifier_ready": get_quickdraw_classifier().is_ready,
            "clip_ready": get_clip_word_ranker().is_ready,
        }

    return app


app = create_app()

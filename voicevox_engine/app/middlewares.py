"""FastAPI ミドルウェア"""

import re
import warnings
from collections.abc import Awaitable, Callable
from traceback import print_exception

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.errors import ServerErrorMiddleware

from voicevox_engine.setting.model import CorsPolicyMode


def configure_middlewares(
    app: FastAPI, cors_policy_mode: CorsPolicyMode, allow_origin: list[str] | None
) -> FastAPI:
    """FastAPI のミドルウェアを設定する。"""

    # 未処理の例外が発生するとCORSMiddlewareが適用されない問題に対するワークアラウンド
    # ref: https://github.com/VOICEVOX/voicevox_engine/issues/91
    async def global_execution_handler(request: Request, exc: Exception) -> Response:
        print_exception(exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal Server Error"},
        )

    app.add_middleware(ServerErrorMiddleware, handler=global_execution_handler)

    # CORS用のヘッダを生成するミドルウェア
    localhost_regex = (
        r"^[a-zA-Z+\-\.]+://(([^/]+\.)?localhost|127\.0\.0\.1|\[::1\])(:[0-9]+)?$"
    )
    compiled_localhost_regex = re.compile(localhost_regex)
    allowed_origins = ["*"]
    if cors_policy_mode == "localapps":
        allowed_origins = ["app://."]
        if allow_origin is not None:
            allowed_origins += allow_origin
            if "*" in allow_origin:
                msg = 'Deprecated use of argument "*" in allow_origin. Use option "--cors_policy_mode all" instead.'
                warnings.warn(msg, stacklevel=1)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_origin_regex=localhost_regex,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 許可されていないOriginを遮断するミドルウェア
    @app.middleware("http")
    async def block_origin_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response | JSONResponse:
        is_valid_origin: bool = False
        browser_extensions = [
            "chrome-extension://",
            "moz-extension://",
            "ms-browser-extension://",
            "safari-extension://",
            "safari-web-extension://",
        ]
        if "Origin" not in request.headers:  # Originのない純粋なリクエストの場合
            is_valid_origin = True
        elif "*" in allowed_origins:  # すべてを許可する設定の場合
            is_valid_origin = True
        elif request.headers["Origin"] in allowed_origins:  # Originが許可されている場合
            is_valid_origin = True
        elif compiled_localhost_regex.fullmatch(
            request.headers["Origin"]
        ):  # localhostの場合
            is_valid_origin = True
        elif any(
            request.headers["Origin"].startswith(ext) for ext in browser_extensions
        ):  # ブラウザ拡張の場合
            is_valid_origin = True

        if is_valid_origin:
            return await call_next(request)
        else:
            return JSONResponse(
                status_code=403, content={"detail": "Origin not allowed"}
            )

    return app

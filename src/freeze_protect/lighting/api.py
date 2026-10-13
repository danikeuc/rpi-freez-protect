import asyncio
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from starlette.responses import JSONResponse, Response

from .controller import Clock, LightController, LightError
from .executor import Output, UnavailableOutput
from .models import Action, Event, EventResult, Settings, SettingsUpdate, Status

PREFIX = "/api/v1/lights"


def create_app(
    database_path: Path,
    display_token: str | None = None,
    settings_token: str | None = None,
    camera_token: str | None = None,
    executor: Output | None = None,
    allowed_sources: set[str] | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    tokens = {
        "display": display_token,
        "settings": settings_token,
        "camera": camera_token,
    }
    configured = (
        all(
            isinstance(t, str) and t.isascii() and 32 <= len(t) <= 512
            for t in tokens.values()
        )
        and len(set(tokens.values())) == 3
        and bool(allowed_sources)
        and executor is not None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        controller = await asyncio.to_thread(
            LightController,
            database_path,
            executor or UnavailableOutput(),
            allowed_sources or set(),
            clock,
            configured,
        )
        app.state.light_controller = controller

        async def worker() -> None:
            while True:
                await asyncio.to_thread(controller.tick)
                await asyncio.sleep(0.25)

        task = asyncio.create_task(worker())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            await asyncio.to_thread(controller.close)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def bounded_body(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                return JSONResponse({"detail": "body_too_large"}, status_code=413)
        request._body = bytes(body)
        return await call_next(request)

    @app.exception_handler(LightError)
    async def error_handler(request: Request, error: LightError) -> JSONResponse:
        return JSONResponse({"detail": error.reason}, status_code=error.code)

    def authorize(*roles: str) -> Callable[[Request], None]:
        def check(request: Request) -> None:
            header = request.headers.get("authorization", "")
            if not header.startswith("Bearer ") or len(header) > 1024:
                raise HTTPException(401, "authentication_required")
            supplied = header[7:]
            if not supplied.isascii():
                raise HTTPException(401, "authentication_failed")
            matches = [
                role
                for role, token in tokens.items()
                if token
                and len(token) >= 32
                and secrets.compare_digest(supplied, token)
            ]
            if not matches:
                raise HTTPException(401, "authentication_failed")
            if not any(role in roles for role in matches):
                raise HTTPException(403, "role_forbidden")

        return check

    def controller(request: Request) -> LightController:
        value: LightController = request.app.state.light_controller
        return value

    @app.get(
        PREFIX + "/status", dependencies=[Depends(authorize("display", "settings"))]
    )
    def status(c: Annotated[LightController, Depends(controller)]) -> Status:
        return c.status()

    @app.post(PREFIX + "/actions", dependencies=[Depends(authorize("display"))])
    def actions(
        body: Action, c: Annotated[LightController, Depends(controller)]
    ) -> Status:
        return c.actions(body)

    @app.get(PREFIX + "/settings", dependencies=[Depends(authorize("settings"))])
    def settings(c: Annotated[LightController, Depends(controller)]) -> Settings:
        return c.settings()

    @app.put(PREFIX + "/settings", dependencies=[Depends(authorize("settings"))])
    def update_settings(
        body: SettingsUpdate, c: Annotated[LightController, Depends(controller)]
    ) -> Settings:
        return c.update_settings(body)

    @app.get(PREFIX + "/history", dependencies=[Depends(authorize("settings"))])
    def history(
        c: Annotated[LightController, Depends(controller)],
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0, le=1000000)] = 0,
    ) -> dict[str, Any]:
        return c.history(limit, offset)

    @app.post(PREFIX + "/events/unifi", dependencies=[Depends(authorize("camera"))])
    def events(
        body: Event, c: Annotated[LightController, Depends(controller)]
    ) -> EventResult:
        return c.events(body)

    return app

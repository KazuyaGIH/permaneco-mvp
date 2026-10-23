import logging

from fastapi import FastAPI, Request

from app.routes import admin, auth, chat, consents, plans, students, tutors

app = FastAPI(title="Permaneço API", docs_url=None, redoc_url=None)
logger = logging.getLogger("app.request")


@app.middleware("http")
async def safe_request_logging(request: Request, call_next):
    response = await call_next(request)
    route = request.scope.get("route")
    route_path = getattr(route, "path", "/unmatched")
    logger.info("%s %s %s", request.method, route_path, response.status_code)
    return response


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(students.router)
app.include_router(tutors.router)
app.include_router(admin.router)
app.include_router(consents.router)
app.include_router(chat.router)
app.include_router(plans.router)

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent import AgentService
from app.config import get_settings
from app.models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentRunRequest,
    AgentRunResponse,
    ImportedWorkflowTemplate,
    SnowflakeMetadataResponse,
    SnowflakeSelection,
)
from app.n8n_importer import load_workflow_templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Best-effort init on startup; lazy fallback handles cold starts on Vercel
    try:
        settings = get_settings()
        app.state.agent_service = AgentService(settings)
    except Exception:
        app.state.agent_service = None
    yield


app = FastAPI(title="Agentic Garden API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dist = Path(__file__).resolve().parent / "static"
frontend_assets = frontend_dist / "assets"


def get_agent_service() -> AgentService:
    """Lazy init — handles Vercel cold starts where lifespan may not have run."""
    service = getattr(app.state, "agent_service", None)
    if service is None:
        app.state.agent_service = AgentService(get_settings())
    return app.state.agent_service


@app.get("/debug")
async def debug():
    return {
        "frontend_dist": str(frontend_dist),
        "exists": frontend_dist.exists(),
        "index_exists": (frontend_dist / "index.html").exists(),
    }


if frontend_assets.exists():
    app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/workflows/imported", response_model=list[ImportedWorkflowTemplate])
async def imported_workflows() -> list[ImportedWorkflowTemplate]:
    return load_workflow_templates()


@app.get("/snowflake/metadata", response_model=SnowflakeMetadataResponse)
async def snowflake_metadata(
    role: str | None = None,
    warehouse: str | None = None,
    database: str | None = None,
    schema: str | None = None,
) -> SnowflakeMetadataResponse:
    service = get_agent_service()
    try:
        return service.get_snowflake_metadata(
            SnowflakeSelection(
                role=role,
                warehouse=warehouse,
                database=database,
                schema_name=schema,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/agent/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    service = get_agent_service()
    try:
        return service.run(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/agent/chat", response_model=AgentChatResponse)
async def chat_with_run(request: AgentChatRequest) -> AgentChatResponse:
    service = get_agent_service()
    try:
        return service.chat(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/{full_path:path}")
async def frontend_app(full_path: str):
    index_file = frontend_dist / "index.html"
    if index_file.exists() and not full_path.startswith(("agent", "health", "workflows")):
        return FileResponse(index_file)
    return {"detail": "Not Found"}


def main() -> None:
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)

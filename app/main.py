from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.agent import AgentService
from app.config import get_settings
from app.models import AgentRunRequest, AgentRunResponse, ImportedWorkflowTemplate
from app.n8n_importer import load_workflow_templates

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.agent_service = AgentService(settings)
    yield


app = FastAPI(title="Agentic Garden API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

frontend_dist = Path(__file__).resolve().parents[1] / "frontend" / "dist"
frontend_assets = frontend_dist / "assets"
if frontend_assets.exists():
    app.mount("/assets", StaticFiles(directory=frontend_assets), name="frontend-assets")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/workflows/imported", response_model=list[ImportedWorkflowTemplate])
async def imported_workflows() -> list[ImportedWorkflowTemplate]:
    return load_workflow_templates()


@app.post("/agent/run", response_model=AgentRunResponse)
async def run_agent(request: AgentRunRequest) -> AgentRunResponse:
    service: AgentService = app.state.agent_service
    try:
        return service.run(request)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/{full_path:path}")
async def frontend_app(full_path: str):
    index_file = frontend_dist / "index.html"
    if index_file.exists() and not full_path.startswith(("agent", "health", "workflows")):
        return FileResponse(index_file)
    return {"detail": "Not Found"}


def main() -> None:
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)

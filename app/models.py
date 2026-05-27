from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class LlmConfig(BaseModel):
    provider: Literal["openai", "google", "groq"] = "openai"
    model: str | None = None
    api_key: str | None = None


class EmailInput(BaseModel):
    action: Literal["send", "draft", "reply"] = "send"
    to: list[EmailStr] = Field(default_factory=list)
    cc: list[EmailStr] = Field(default_factory=list)
    bcc: list[EmailStr] = Field(default_factory=list)
    subject: str | None = None
    instructions: str = Field(
        default="Summarize the query results and explain any notable patterns."
    )
    thread_id: str | None = None
    reply_to_message_id: str | None = None


class ChartSpec(BaseModel):
    chart_type: Literal["bar", "line", "pie", "area"] = "bar"
    title: str
    x_key: str
    y_key: str
    data: list[dict[str, Any]] = Field(default_factory=list)


class AgentRunRequest(BaseModel):
    workflow_nodes: list[str] = Field(default_factory=list)
    sql_query: str = Field(..., description="The SQL query to execute in Snowflake.")
    max_rows: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of rows to retrieve from Snowflake.",
    )
    reasoning_goal: str = Field(
        default="Analyze the dataset and prepare a concise email for stakeholders."
    )
    llm: LlmConfig = Field(default_factory=LlmConfig)
    email: EmailInput = Field(default_factory=EmailInput)
    memory_session_key: str | None = None
    output_parser_schema: str | None = None


class EmailExecutionResult(BaseModel):
    action: str
    message_id: str | None = None
    draft_id: str | None = None
    thread_id: str | None = None
    status: str


class TokenUsageMetrics(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int | None = None
    cache_read_tokens: int | None = None


class MonitoringStage(BaseModel):
    key: str
    label: str
    status: Literal["completed", "skipped", "error"] = "completed"
    started_at: str
    completed_at: str
    duration_ms: int = 0
    provider: str | None = None
    model: str | None = None
    run_type: str | None = None
    prompt_preview: str | None = None
    prompt_chars: int | None = None
    output_preview: str | None = None
    row_count: int | None = None
    usage: TokenUsageMetrics | None = None


class MonitoringOverview(BaseModel):
    started_at: str
    completed_at: str
    total_duration_ms: int
    provider: str
    model: str
    workflow_nodes: list[str] = Field(default_factory=list)
    row_count: int = 0
    chart_count: int = 0
    structured_output_available: bool = False
    trace_count: int = 1
    llm_call_count: int = 0
    tool_call_count: int = 0
    error_count: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    accuracy_score: float | None = None
    feedback_status: str = "Pending evaluation"


class LangSmithMonitoringStatus(BaseModel):
    enabled: bool = False
    sdk_available: bool = False
    api_key_configured: bool = False
    project_name: str | None = None
    endpoint: str | None = None
    status_label: str
    dashboard_sections: list[str] = Field(default_factory=list)
    suggested_metrics: list[str] = Field(default_factory=list)


class MonitoringPayload(BaseModel):
    overview: MonitoringOverview
    stages: list[MonitoringStage] = Field(default_factory=list)
    langsmith: LangSmithMonitoringStatus


class AgentRunResponse(BaseModel):
    run_id: str
    executed_nodes: list[str]
    sql_query: str
    row_count: int
    analysis: str
    charts: list[ChartSpec] = Field(default_factory=list)
    generated_subject: str
    generated_body: str
    email_result: EmailExecutionResult | None = None
    sample_rows: list[dict[str, Any]]
    structured_output: dict[str, Any] | None = None
    monitoring: MonitoringPayload


class AgentChatRequest(BaseModel):
    run_id: str
    message: str = Field(..., min_length=1)
    llm: LlmConfig = Field(default_factory=LlmConfig)
    memory_session_key: str | None = None


class AgentChatResponse(BaseModel):
    run_id: str
    answer: str


class ImportedNodeDefinition(BaseModel):
    type_id: str
    title: str
    category: str
    subtitle: str
    color: str
    supported: bool = False
    origin_type: str | None = None


class ImportedCanvasNode(BaseModel):
    id: str
    type_id: str
    name: str
    x: float
    y: float
    config: dict[str, Any] = Field(default_factory=dict)


class ImportedCanvasEdge(BaseModel):
    id: str
    source: str
    target: str
    connection_type: str


class ImportedWorkflowTemplate(BaseModel):
    id: str
    name: str
    source_file: str
    executable_nodes: list[str] = Field(default_factory=list)
    node_definitions: list[ImportedNodeDefinition] = Field(default_factory=list)
    nodes: list[ImportedCanvasNode] = Field(default_factory=list)
    edges: list[ImportedCanvasEdge] = Field(default_factory=list)
    form_prefill: dict[str, Any] = Field(default_factory=dict)

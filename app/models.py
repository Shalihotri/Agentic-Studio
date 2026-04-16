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
    workflow_nodes: list[Literal["snowflake", "reasoning", "gmail"]] = Field(
        default_factory=list
    )
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


class EmailExecutionResult(BaseModel):
    action: str
    message_id: str | None = None
    draft_id: str | None = None
    thread_id: str | None = None
    status: str


class AgentRunResponse(BaseModel):
    executed_nodes: list[str]
    sql_query: str
    row_count: int
    analysis: str
    charts: list[ChartSpec] = Field(default_factory=list)
    generated_subject: str
    generated_body: str
    email_result: EmailExecutionResult | None = None
    sample_rows: list[dict[str, Any]]


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

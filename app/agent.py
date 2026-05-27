import json
import uuid
from contextlib import nullcontext
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langsmith import tracing_context
from pydantic import BaseModel, Field

from app.config import Settings
from app.connectors.gmail import GmailClient
from app.connectors.outlook import OutlookClient
from app.connectors.snowflake import SnowflakeClient
from app.models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentRunRequest,
    AgentRunResponse,
    ChartSpec,
    EmailExecutionResult,
    LangSmithMonitoringStatus,
    MonitoringOverview,
    MonitoringPayload,
    MonitoringStage,
    TokenUsageMetrics,
)


class EmailDraftPlan(BaseModel):
    analysis: str = Field(description="The business analysis derived from the data.")
    subject: str = Field(description="The email subject line.")
    body: str = Field(description="The email body text.")


class ChartSpecRaw(BaseModel):
    chart_type: str = Field(description="One of: bar, line, pie, area")
    title: str = Field(description="Chart title.")
    x_key: str = Field(description="The data key to use for the X axis / category.")
    y_key: str = Field(description="The data key to use for the Y axis / value.")


class ChartsPlan(BaseModel):
    charts: list[ChartSpecRaw] = Field(
        description="List of 1-3 charts that best visualise the data."
    )


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._snowflake = SnowflakeClient(settings)
        self._gmail = GmailClient(settings)
        self._outlook = OutlookClient(settings)
        self._run_store: dict[str, dict[str, Any]] = {}
        self._chat_sessions: dict[str, list[Any]] = {}

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        return max(1, round(len(text) / 4)) if text else 0

    @staticmethod
    def _trim_preview(value: str | None, limit: int = 700) -> str | None:
        if not value:
            return None
        text = value.strip()
        if len(text) <= limit:
            return text
        return f"{text[:limit].rstrip()}..."

    @staticmethod
    def _stringify_output(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if hasattr(value, "model_dump"):
            return json.dumps(value.model_dump(), default=str)
        return json.dumps(value, default=str)

    @staticmethod
    def _coerce_usage(value: Any) -> TokenUsageMetrics | None:
        if not value:
            return None
        if isinstance(value, TokenUsageMetrics):
            return value
        data = dict(value)
        input_details = data.get("input_token_details") or {}
        output_details = data.get("output_token_details") or {}
        input_tokens = int(data.get("input_tokens") or 0)
        output_tokens = int(data.get("output_tokens") or 0)
        total_tokens = int(data.get("total_tokens") or input_tokens + output_tokens)
        return TokenUsageMetrics(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            reasoning_tokens=output_details.get("reasoning"),
            cache_read_tokens=input_details.get("cache_read"),
        )

    def _usage_or_estimate(
        self, raw_message: Any, prompt_text: str = "", output_text: str = ""
    ) -> TokenUsageMetrics:
        usage = self._coerce_usage(getattr(raw_message, "usage_metadata", None))
        if usage:
            return usage
        prompt_tokens = self._estimate_token_count(prompt_text)
        output_tokens = self._estimate_token_count(output_text)
        return TokenUsageMetrics(
            input_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_tokens=prompt_tokens + output_tokens,
        )

    def _build_stage(
        self,
        *,
        key: str,
        label: str,
        started_at: str,
        start_perf: float,
        provider: str | None = None,
        model: str | None = None,
        run_type: str | None = None,
        prompt_text: str | None = None,
        output_text: str | None = None,
        row_count: int | None = None,
        usage: TokenUsageMetrics | None = None,
        status: str = "completed",
    ) -> MonitoringStage:
        return MonitoringStage(
            key=key,
            label=label,
            status=status,
            started_at=started_at,
            completed_at=self._now_iso(),
            duration_ms=round((perf_counter() - start_perf) * 1000),
            provider=provider,
            model=model,
            run_type=run_type,
            prompt_preview=self._trim_preview(prompt_text),
            prompt_chars=len(prompt_text) if prompt_text else None,
            output_preview=self._trim_preview(output_text),
            row_count=row_count,
            usage=usage,
        )

    def _langsmith_status(self) -> LangSmithMonitoringStatus:
        enabled = bool(
            self._settings.langsmith_tracing and self._settings.langsmith_api_key
        )
        return LangSmithMonitoringStatus(
            enabled=enabled,
            sdk_available=True,
            api_key_configured=bool(self._settings.langsmith_api_key),
            project_name=self._settings.langsmith_project or None,
            endpoint=self._settings.langsmith_endpoint,
            status_label=(
                "Tracing active"
                if enabled
                else "Tracing configured partially"
                if self._settings.langsmith_api_key
                else "Tracing not configured"
            ),
            dashboard_sections=[
                "Traces",
                "LLM Calls",
                "Cost & Tokens",
                "Feedback",
                "Run Types",
            ],
            suggested_metrics=[
                "trace count",
                "latency",
                "error rate",
                "token usage",
                "cost",
                "tool performance",
                "feedback scores",
                "online evaluator accuracy",
            ],
        )

    def _get_llm(self, request: AgentRunRequest | AgentChatRequest) -> BaseChatModel:
        provider = request.llm.provider
        model_name = request.llm.model

        if provider == "google":
            return ChatGoogleGenerativeAI(
                model=model_name or self._settings.google_model,
                api_key=request.llm.api_key or self._settings.google_api_key,
            )

        if provider == "groq":
            return ChatGroq(
                model=model_name or self._settings.groq_model,
                api_key=request.llm.api_key or self._settings.groq_api_key,
            )

        kwargs: dict[str, Any] = {
            "model": model_name or self._settings.openai_model,
            "api_key": request.llm.api_key or self._settings.openai_api_key,
        }
        if self._settings.openai_base_url:
            kwargs["base_url"] = self._settings.openai_base_url
        return ChatOpenAI(**kwargs)

    def _build_reasoning_agent(
        self, request: AgentRunRequest, rows: list[dict[str, Any]]
    ):
        llm = self._get_llm(request)

        @tool
        def profile_query_results() -> str:
            """Return dataset shape and representative samples from the Snowflake query result."""
            if not rows:
                return json.dumps({"row_count": 0, "columns": [], "sample_rows": []})

            return json.dumps(
                {
                    "row_count": len(rows),
                    "columns": list(rows[0].keys()),
                    "sample_rows": rows[:5],
                },
                default=str,
            )

        return create_react_agent(llm, [profile_query_results])

    def _structured_invoke(
        self, request: AgentRunRequest, schema: type[BaseModel], prompt: str
    ) -> tuple[Any, Any, TokenUsageMetrics]:
        runnable = self._get_llm(request).with_structured_output(
            schema, include_raw=True
        )
        response = runnable.invoke(prompt)
        parsed = response.get("parsed") if isinstance(response, dict) else response
        raw = response.get("raw") if isinstance(response, dict) else None
        if parsed is None:
            raise ValueError("Structured output parsing failed for the LLM response.")
        usage = self._usage_or_estimate(
            raw,
            prompt_text=prompt,
            output_text=self._stringify_output(parsed),
        )
        return parsed, raw, usage

    def _run_output_parser(
        self,
        request: AgentRunRequest,
        analysis: str,
        rows: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, MonitoringStage | None]:
        schema = (request.output_parser_schema or "").strip()
        if not schema:
            return None, None

        llm = self._get_llm(request)
        parser_prompt = f"""
Return JSON only that matches this schema exactly.

Schema:
{schema}

Reasoning goal:
{request.reasoning_goal}

Analysis:
{analysis}

Sample rows:
{json.dumps(rows[:5], default=str)}
""".strip()

        started_at = self._now_iso()
        start_perf = perf_counter()
        raw = llm.invoke([HumanMessage(content=parser_prompt)])
        content = raw.content if isinstance(raw.content, str) else json.dumps(raw.content)
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            parts = content.split("\n", 1)
            content = parts[1] if len(parts) > 1 else parts[0]
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = {"raw": content}

        stage = self._build_stage(
            key="output_parser",
            label="Structured Output Parser",
            started_at=started_at,
            start_perf=start_perf,
            provider=request.llm.provider,
            model=request.llm.model or None,
            run_type="llm",
            prompt_text=parser_prompt,
            output_text=self._stringify_output(parsed),
            row_count=len(rows),
            usage=self._usage_or_estimate(
                raw, prompt_text=parser_prompt, output_text=content
            ),
        )
        return parsed, stage

    def _run_reasoning(
        self, request: AgentRunRequest, rows: list[dict[str, Any]]
    ) -> tuple[
        str,
        str,
        str,
        list[ChartSpec],
        dict[str, Any] | None,
        list[MonitoringStage],
    ]:
        agent = self._build_reasoning_agent(request, rows)
        reasoning_prompt = f"""
You are preparing a stakeholder email from Snowflake query results.

Reasoning goal:
{request.reasoning_goal}

Email instructions:
{request.email.instructions}

SQL query:
{request.sql_query}

You must use the `profile_query_results` tool before answering.
Return a concise analysis that highlights the main findings, risks, trends, or anomalies worth emailing.
""".strip()
        stages: list[MonitoringStage] = []

        reasoning_started_at = self._now_iso()
        reasoning_start_perf = perf_counter()
        agent_result = agent.invoke({"messages": [HumanMessage(content=reasoning_prompt)]})
        final_message = agent_result["messages"][-1]
        analysis = final_message.content
        if not isinstance(analysis, str):
            analysis = str(analysis)
        stages.append(
            self._build_stage(
                key="reasoning",
                label="Reasoning Analysis",
                started_at=reasoning_started_at,
                start_perf=reasoning_start_perf,
                provider=request.llm.provider,
                model=request.llm.model or None,
                run_type="llm",
                prompt_text=reasoning_prompt,
                output_text=analysis,
                row_count=len(rows),
                usage=self._usage_or_estimate(
                    final_message, prompt_text=reasoning_prompt, output_text=analysis
                ),
            )
        )

        email_prompt = f"""
Draft an email based on this analysis.

Action: {request.email.action}
User-provided subject override: {request.email.subject or "None"}
Email instructions: {request.email.instructions}
Analysis:
{analysis}

Requirements:
- Keep the tone professional.
- If the user provided a subject override, reuse it exactly.
- The body should be ready to send as plain text.
""".strip()
        email_started_at = self._now_iso()
        email_start_perf = perf_counter()
        email_plan, _, email_usage = self._structured_invoke(
            request, EmailDraftPlan, email_prompt
        )
        stages.append(
            self._build_stage(
                key="email_generation",
                label="Email Generation",
                started_at=email_started_at,
                start_perf=email_start_perf,
                provider=request.llm.provider,
                model=request.llm.model or None,
                run_type="llm",
                prompt_text=email_prompt,
                output_text=self._stringify_output(email_plan),
                row_count=len(rows),
                usage=email_usage,
            )
        )

        charts: list[ChartSpec] = []
        try:
            columns = list(rows[0].keys()) if rows else []
            sample = rows[:20]
            charts_prompt = f"""
You are a data visualisation expert. Given this dataset, suggest 1-3 charts.

Columns available: {columns}
Sample data (up to 20 rows): {json.dumps(sample, default=str)}
Analysis summary: {analysis}

Rules:
- Only use column names that actually exist in the data above.
- x_key must be a categorical or date column.
- y_key must be a numeric column.
- Choose chart_type from: bar, line, pie, area.
- Pick the chart types that best suit the data shape.
- Give each chart a short descriptive title.
""".strip()
            charts_started_at = self._now_iso()
            charts_start_perf = perf_counter()
            charts_plan, _, charts_usage = self._structured_invoke(
                request, ChartsPlan, charts_prompt
            )
            for spec in charts_plan.charts:
                chart_type = (
                    spec.chart_type
                    if spec.chart_type in ("bar", "line", "pie", "area")
                    else "bar"
                )
                chart_data = []
                for row in rows:
                    x_val = row.get(spec.x_key)
                    y_val = row.get(spec.y_key)
                    if y_val is None:
                        continue
                    try:
                        y_num = float(y_val)
                    except (TypeError, ValueError):
                        continue
                    chart_data.append(
                        {
                            spec.x_key: str(x_val) if x_val is not None else "",
                            spec.y_key: y_num,
                        }
                    )
                charts.append(
                    ChartSpec(
                        chart_type=chart_type,
                        title=spec.title,
                        x_key=spec.x_key,
                        y_key=spec.y_key,
                        data=chart_data,
                    )
                )
            stages.append(
                self._build_stage(
                    key="chart_planning",
                    label="Chart Planning",
                    started_at=charts_started_at,
                    start_perf=charts_start_perf,
                    provider=request.llm.provider,
                    model=request.llm.model or None,
                    run_type="llm",
                    prompt_text=charts_prompt,
                    output_text=self._stringify_output(charts_plan),
                    row_count=len(rows),
                    usage=charts_usage,
                )
            )
        except Exception:
            pass

        structured_output, parser_stage = self._run_output_parser(request, analysis, rows)
        if parser_stage:
            stages.append(parser_stage)

        return (
            email_plan.analysis,
            email_plan.subject,
            email_plan.body,
            charts,
            structured_output,
            stages,
        )

    def _run_email(
        self,
        request: AgentRunRequest,
        generated_subject: str,
        generated_body: str,
        provider: str,
    ) -> EmailExecutionResult:
        email = request.email
        client = self._gmail if provider == "gmail" else self._outlook

        if email.action == "draft":
            return client.create_draft(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        if email.action == "reply":
            return client.reply_message(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        return client.send_message(
            to=[str(item) for item in email.to],
            cc=[str(item) for item in email.cc],
            bcc=[str(item) for item in email.bcc],
            subject=generated_subject,
            body=generated_body,
            thread_id=email.thread_id,
            reply_to_message_id=email.reply_to_message_id,
        )

    def run(self, request: AgentRunRequest) -> AgentRunResponse:
        requested_nodes = request.workflow_nodes or ["snowflake", "reasoning", "gmail"]
        rows: list[dict[str, Any]] = []
        analysis = ""
        charts: list[ChartSpec] = []
        generated_subject = request.email.subject or ""
        generated_body = ""
        email_result: EmailExecutionResult | None = None
        structured_output: dict[str, Any] | None = None
        monitoring_stages: list[MonitoringStage] = []
        run_started_at = self._now_iso()
        run_start_perf = perf_counter()
        llm_model = request.llm.model or getattr(
            self._settings, f"{request.llm.provider}_model", ""
        )

        trace_ctx = (
            tracing_context(
                project_name=self._settings.langsmith_project,
                enabled=True,
                tags=["agentic-garden", "workflow-run"],
                metadata={
                    "provider": request.llm.provider,
                    "workflow_nodes": requested_nodes,
                },
            )
            if self._settings.langsmith_tracing and self._settings.langsmith_api_key
            else nullcontext()
        )

        with trace_ctx:
            for node in requested_nodes:
                if node == "snowflake":
                    started_at = self._now_iso()
                    start_perf = perf_counter()
                    rows = self._snowflake.run_query(request.sql_query, request.max_rows)
                    monitoring_stages.append(
                        self._build_stage(
                            key="snowflake",
                            label="Snowflake Query",
                            started_at=started_at,
                            start_perf=start_perf,
                            run_type="tool",
                            prompt_text=request.sql_query,
                            output_text=f"{len(rows)} rows returned",
                            row_count=len(rows),
                        )
                    )
                    continue

                if node in {"chat_model", "memory", "output_parser"}:
                    continue

                if node == "reasoning":
                    if not rows:
                        raise ValueError(
                            "Reasoning node requires Snowflake data first. Add and configure a Snowflake node."
                        )
                    (
                        analysis,
                        generated_subject,
                        generated_body,
                        charts,
                        structured_output,
                        reasoning_stages,
                    ) = self._run_reasoning(request, rows)
                    monitoring_stages.extend(reasoning_stages)
                    continue

                if node in {"gmail", "outlook"}:
                    if not rows and not generated_body:
                        raise ValueError(
                            f"{node.title()} node requires upstream data or reasoning. Add a Snowflake or Reasoning node first."
                        )
                    if not generated_body:
                        generated_body = (
                            "Attached are the latest Snowflake query results.\n\n"
                            f"Rows returned: {len(rows)}"
                        )
                    started_at = self._now_iso()
                    start_perf = perf_counter()
                    email_result = self._run_email(
                        request,
                        generated_subject or request.email.subject or "Snowflake update",
                        generated_body,
                        node,
                    )
                    monitoring_stages.append(
                        self._build_stage(
                            key=node,
                            label=f"{node.title()} Delivery",
                            started_at=started_at,
                            start_perf=start_perf,
                            run_type="tool",
                            output_text=self._stringify_output(email_result.model_dump()),
                            row_count=len(rows),
                        )
                    )

        prompt_tokens = sum(
            stage.usage.input_tokens for stage in monitoring_stages if stage.usage
        )
        completion_tokens = sum(
            stage.usage.output_tokens for stage in monitoring_stages if stage.usage
        )
        total_tokens = sum(
            stage.usage.total_tokens for stage in monitoring_stages if stage.usage
        )
        monitoring = MonitoringPayload(
            overview=MonitoringOverview(
                started_at=run_started_at,
                completed_at=self._now_iso(),
                total_duration_ms=round((perf_counter() - run_start_perf) * 1000),
                provider=request.llm.provider,
                model=llm_model,
                workflow_nodes=requested_nodes,
                row_count=len(rows),
                chart_count=len(charts),
                structured_output_available=structured_output is not None,
                llm_call_count=sum(
                    1 for stage in monitoring_stages if stage.run_type == "llm"
                ),
                tool_call_count=sum(
                    1 for stage in monitoring_stages if stage.run_type == "tool"
                ),
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
            ),
            stages=monitoring_stages,
            langsmith=self._langsmith_status(),
        )

        run_id = str(uuid.uuid4())
        session_key = request.memory_session_key or run_id
        self._run_store[run_id] = {
            "sql_query": request.sql_query,
            "rows": rows,
            "analysis": analysis,
            "charts": [chart.model_dump() for chart in charts],
            "structured_output": structured_output,
            "session_key": session_key,
            "monitoring": monitoring.model_dump(),
        }
        self._chat_sessions[session_key] = []

        return AgentRunResponse(
            run_id=run_id,
            executed_nodes=requested_nodes,
            sql_query=request.sql_query,
            row_count=len(rows),
            analysis=analysis,
            charts=charts,
            generated_subject=generated_subject,
            generated_body=generated_body,
            email_result=email_result,
            sample_rows=rows,
            structured_output=structured_output,
            monitoring=monitoring,
        )

    def chat(self, request: AgentChatRequest) -> AgentChatResponse:
        run_context = self._run_store.get(request.run_id)
        if not run_context:
            raise ValueError("Run context not found. Run the workflow again before chatting.")

        session_key = request.memory_session_key or run_context["session_key"]
        history = self._chat_sessions.setdefault(session_key, [])

        prompt = f"""
You are answering follow-up questions about a workflow run.
Use only the workflow context below. If the answer is not supported by the context, say so plainly.

SQL query:
{run_context["sql_query"]}

Analysis:
{run_context["analysis"]}

Structured output:
{json.dumps(run_context["structured_output"], default=str)}

Sample rows:
{json.dumps(run_context["rows"][:20], default=str)}

Charts:
{json.dumps(run_context["charts"], default=str)}
""".strip()

        messages = [HumanMessage(content=prompt), *history, HumanMessage(content=request.message)]
        response = self._get_llm(request).invoke(messages)
        answer = response.content if isinstance(response.content, str) else str(response.content)

        history.append(HumanMessage(content=request.message))
        history.append(AIMessage(content=answer))

        return AgentChatResponse(run_id=request.run_id, answer=answer)

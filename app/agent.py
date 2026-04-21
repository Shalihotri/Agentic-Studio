import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from app.config import Settings
from app.connectors.gmail import GmailClient
from app.connectors.snowflake import SnowflakeClient
from app.models import AgentRunRequest, AgentRunResponse, ChartSpec, EmailExecutionResult


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
        description="List of 1–3 charts that best visualise the data."
    )


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._snowflake = SnowflakeClient(settings)
        self._gmail = GmailClient(settings)

    def _get_llm(self, request: AgentRunRequest) -> BaseChatModel:
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

    def _run_reasoning(
        self, request: AgentRunRequest, rows: list[dict[str, Any]]
    ) -> tuple[str, str, str, list[ChartSpec]]:
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
        agent_result = agent.invoke(
            {"messages": [HumanMessage(content=reasoning_prompt)]}
        )
        analysis = agent_result["messages"][-1].content

        structured_llm = self._get_llm(request).with_structured_output(EmailDraftPlan)
        email_plan = structured_llm.invoke(
            f"""
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
"""
        )

        # Generate chart specs based on the actual data columns and values
        charts: list[ChartSpec] = []
        try:
            columns = list(rows[0].keys()) if rows else []
            sample = rows[:20]
            charts_llm = self._get_llm(request).with_structured_output(ChartsPlan)
            charts_plan = charts_llm.invoke(
                f"""
You are a data visualisation expert. Given this dataset, suggest 1–3 charts.

Columns available: {columns}
Sample data (up to 20 rows): {json.dumps(sample, default=str)}
Analysis summary: {analysis}

Rules:
- Only use column names that actually exist in the data above.
- x_key must be a categorical or date column.
- y_key must be a numeric column.
- Choose chart_type from: bar, line, pie, area.
- Pick the chart types that best suit the data shape (bar for comparisons, line/area for trends, pie for proportions with ≤8 categories).
- Give each chart a short descriptive title.
"""
            )
            # Build ChartSpec objects with the actual data attached
            for spec in charts_plan.charts:
                chart_type = spec.chart_type if spec.chart_type in ("bar", "line", "pie", "area") else "bar"
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
                    chart_data.append({
                        spec.x_key: str(x_val) if x_val is not None else "",
                        spec.y_key: y_num,
                    })
                charts.append(ChartSpec(
                    chart_type=chart_type,
                    title=spec.title,
                    x_key=spec.x_key,
                    y_key=spec.y_key,
                    data=chart_data,
                ))
        except Exception:
            pass  # charts are best-effort; never crash the workflow

        return email_plan.analysis, email_plan.subject, email_plan.body, charts

    def _run_email(
        self,
        request: AgentRunRequest,
        generated_subject: str,
        generated_body: str,
    ) -> EmailExecutionResult:
        email = request.email

        if email.action == "draft":
            return self._gmail.create_draft(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        if email.action == "reply":
            return self._gmail.reply_message(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        return self._gmail.send_message(
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

        for node in requested_nodes:
            if node == "snowflake":
                rows = self._snowflake.run_query(request.sql_query, request.max_rows)
                continue

            if node == "reasoning":
                if not rows:
                    raise ValueError(
                        "Reasoning node requires Snowflake data first. Add and configure a Snowflake node."
                    )
                analysis, generated_subject, generated_body, charts = self._run_reasoning(
                    request, rows
                )
                continue

            if node == "gmail":
                if not rows and not generated_body:
                    raise ValueError(
                        "Gmail node requires upstream data or reasoning. Add a Snowflake or Reasoning node first."
                    )
                if not generated_body:
                    generated_body = (
                        "Attached are the latest Snowflake query results.\n\n"
                        f"Rows returned: {len(rows)}"
                    )
                email_result = self._run_email(
                    request,
                    generated_subject or request.email.subject or "Snowflake update",
                    generated_body,
                )

        return AgentRunResponse(
            executed_nodes=requested_nodes,
            sql_query=request.sql_query,
            row_count=len(rows),
            analysis=analysis,
            charts=charts,
            generated_subject=generated_subject,
            generated_body=generated_body,
            email_result=email_result,
            sample_rows=rows,
        )


from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel, Field

from app.config import Settings
from app.connectors.gmail import GmailClient
from app.connectors.snowflake import SnowflakeClient
from app.models import AgentRunRequest, AgentRunResponse, EmailExecutionResult


class EmailDraftPlan(BaseModel):
    analysis: str = Field(description="The business analysis derived from the data.")
    subject: str = Field(description="The email subject line.")
    body: str = Field(description="The email body text.")


class AgentService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._snowflake = SnowflakeClient(settings)
        self._gmail = GmailClient(settings)

    def _get_llm(self, request: AgentRunRequest) -> BaseChatModel:
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
                return json.dumps(
                    {
                        "row_count": 0,
                        "columns": [],
                        "sample_rows": [],
                    }
                )

            return json.dumps(
                {
                    "row_count": len(rows),
                    "columns": list(rows[0].keys()),
                    "sample_rows": rows[:5],
                },
                default=str,
            )

        return create_react_agent(llm, [profile_query_results])

    def _run_reasoning(
        self, request: AgentRunRequest, rows: list[dict[str, Any]]
    ) -> tuple[str, str, str]:
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
        agent_result = agent.invoke(
            {"messages": [HumanMessage(content=reasoning_prompt)]}
        )
        analysis = agent_result["messages"][-1].content

        structured_llm = self._get_llm(request).with_structured_output(EmailDraftPlan)
        email_plan = structured_llm.invoke(
            f"""
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
"""
        )
        return email_plan.analysis, email_plan.subject, email_plan.body

    def _run_email(
        self,
        request: AgentRunRequest,
        generated_subject: str,
        generated_body: str,
    ) -> EmailExecutionResult:
        email = request.email

        if email.action == "draft":
            return self._gmail.create_draft(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        if email.action == "reply":
            return self._gmail.reply_message(
                to=[str(item) for item in email.to],
                cc=[str(item) for item in email.cc],
                bcc=[str(item) for item in email.bcc],
                subject=generated_subject,
                body=generated_body,
                thread_id=email.thread_id,
                reply_to_message_id=email.reply_to_message_id,
            )

        return self._gmail.send_message(
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
        generated_subject = request.email.subject or ""
        generated_body = ""
        email_result: EmailExecutionResult | None = None

        for node in requested_nodes:
            if node == "snowflake":
                rows = self._snowflake.run_query(request.sql_query, request.max_rows)
                continue

            if node == "reasoning":
                if not rows:
                    raise ValueError(
                        "Reasoning node requires Snowflake data first. Add and configure a Snowflake node."
                    )
                analysis, generated_subject, generated_body = self._run_reasoning(
                    request, rows
                )
                continue

            if node == "gmail":
                if not rows and not generated_body:
                    raise ValueError(
                        "Gmail node requires upstream data or reasoning. Add a Snowflake or Reasoning node first."
                    )
                if not generated_body:
                    generated_body = (
                        "Attached are the latest Snowflake query results.\n\n"
                        f"Rows returned: {len(rows)}"
                    )
                email_result = self._run_email(
                    request,
                    generated_subject or request.email.subject or "Snowflake update",
                    generated_body,
                )

        return AgentRunResponse(
            executed_nodes=requested_nodes,
            sql_query=request.sql_query,
            row_count=len(rows),
            analysis=analysis,
            generated_subject=generated_subject,
            generated_body=generated_body,
            email_result=email_result,
            sample_rows=rows,
        )

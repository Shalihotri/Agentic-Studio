import copy
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from models import (
        ImportedCanvasEdge,
        ImportedCanvasNode,
        ImportedNodeDefinition,
        ImportedWorkflowTemplate,
    )
except ModuleNotFoundError:
    from app.models import (
        ImportedCanvasEdge,
        ImportedCanvasNode,
        ImportedNodeDefinition,
        ImportedWorkflowTemplate,
    )

SUPPORTED_NODE_DEFINITIONS: dict[str, ImportedNodeDefinition] = {
    "snowflake": ImportedNodeDefinition(
        type_id="snowflake",
        title="Snowflake",
        category="Tool Setup",
        subtitle="Warehouse Query",
        color="tool",
        supported=True,
        origin_type="n8n-nodes-base.snowflake",
    ),
    "reasoning": ImportedNodeDefinition(
        type_id="reasoning",
        title="Reasoning",
        category="LLM Setup",
        subtitle="Agent Step",
        color="llm",
        supported=True,
        origin_type="@n8n/n8n-nodes-langchain.agent",
    ),
    "gmail": ImportedNodeDefinition(
        type_id="gmail",
        title="Send Email",
        category="Action Setup",
        subtitle="Gmail Action",
        color="action",
        supported=True,
        origin_type="n8n-nodes-base.gmail",
    ),
}

DEFAULT_FORM_PREFILL = {
    "sql_query": "Provide your SQL Query.",
    "max_rows": 25,
    "reasoning_goal": "Identify the key revenue patterns and write an exec-ready summary.",
    "llm": {
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "api_key": "",
    },
    "email": {
        "action": "send",
        "to": "",
        "cc": "",
        "bcc": "",
        "subject": "Weekly revenue snapshot",
        "instructions": "Keep it concise and call out the top 3 observations.",
        "thread_id": "",
        "reply_to_message_id": "",
    },
}


def _sanitize_type_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"n8n-{slug or 'node'}"


def _title_from_type(n8n_type: str) -> str:
    tail = n8n_type.split(".")[-1]
    words = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", tail).replace("_", " ")
    title = " ".join(part for part in words.split() if part)
    return title[:1].upper() + title[1:] if title else "Imported Node"


def _detect_supported_type(n8n_type: str) -> str | None:
    lowered = n8n_type.lower()
    if "snowflake" in lowered:
        return "snowflake"
    if "gmail" in lowered:
        return "gmail"
    if lowered.endswith(".agent") or "nodes-langchain.agent" in lowered:
        return "reasoning"
    return None


def _detect_model_provider(n8n_type: str) -> str | None:
    lowered = n8n_type.lower()
    if "openai" in lowered:
        return "openai"
    if "google" in lowered or "gemini" in lowered:
        return "google"
    if "groq" in lowered:
        return "groq"
    return None


def _extract_model_name(parameters: dict[str, Any]) -> str | None:
    model = parameters.get("model")
    if isinstance(model, dict):
        value = model.get("value")
        if value:
            return str(value)
    if isinstance(model, str) and model:
        return model
    return None


def _extract_reasoning_goal(parameters: dict[str, Any]) -> str | None:
    text = parameters.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    options = parameters.get("options")
    if isinstance(options, dict):
        system_message = options.get("systemMessage")
        if isinstance(system_message, str) and system_message.strip():
            return system_message.strip()
    return None


def _extract_email_prefill(parameters: dict[str, Any]) -> dict[str, str]:
    email_fields = {
        "to": "",
        "cc": "",
        "bcc": "",
        "subject": "",
        "instructions": "",
        "thread_id": "",
        "reply_to_message_id": "",
        "action": "send",
    }
    key_map = {
        "to": "to",
        "cc": "cc",
        "bcc": "bcc",
        "subject": "subject",
        "message": "instructions",
        "body": "instructions",
        "text": "instructions",
        "threadId": "thread_id",
        "thread_id": "thread_id",
        "replyToMessageId": "reply_to_message_id",
        "reply_to_message_id": "reply_to_message_id",
        "operation": "action",
        "resource": "action",
    }
    for raw_key, target_key in key_map.items():
        value = parameters.get(raw_key)
        if value is None:
            continue
        if isinstance(value, list):
            email_fields[target_key] = ", ".join(str(item) for item in value if item)
        else:
            email_fields[target_key] = str(value)
    return email_fields


def _normalize_positions(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    positions: dict[str, tuple[float, float]] = {}
    xs: list[float] = []
    ys: list[float] = []
    for node in nodes:
        raw_position = node.get("position") or [0, 0]
        x = float(raw_position[0]) if len(raw_position) > 0 else 0.0
        y = float(raw_position[1]) if len(raw_position) > 1 else 0.0
        positions[str(node.get("id"))] = (x, y)
        xs.append(x)
        ys.append(y)

    min_x = min(xs, default=0.0)
    min_y = min(ys, default=0.0)
    return {
        node_id: (x - min_x + 80.0, y - min_y + 80.0)
        for node_id, (x, y) in positions.items()
    }


def _resolve_executable_order(
    parsed_nodes: list[ImportedCanvasNode],
) -> list[str]:
    supported_nodes = [
        node for node in parsed_nodes if node.type_id in SUPPORTED_NODE_DEFINITIONS
    ]
    supported_nodes.sort(key=lambda node: (node.x, node.y))
    return [node.type_id for node in supported_nodes]


def _build_custom_definition(n8n_type: str, fallback_name: str) -> ImportedNodeDefinition:
    return ImportedNodeDefinition(
        type_id=_sanitize_type_id(n8n_type),
        title=fallback_name or _title_from_type(n8n_type),
        category="Imported Nodes",
        subtitle=_title_from_type(n8n_type),
        color="imported",
        supported=False,
        origin_type=n8n_type,
    )


def _collect_reasoning_model(
    node: dict[str, Any],
    incoming_edges: dict[str, list[dict[str, str]]],
    node_by_name: dict[str, dict[str, Any]],
) -> tuple[str | None, str | None]:
    for edge in incoming_edges.get(str(node.get("name")), []):
        if edge["connection_type"] != "ai_languageModel":
            continue
        source_node = node_by_name.get(edge["source_name"])
        if not source_node:
            continue
        provider = _detect_model_provider(str(source_node.get("type", "")))
        model = _extract_model_name(source_node.get("parameters", {}))
        if provider or model:
            return provider, model
    return None, None


def _parse_workflow_file(path: Path) -> ImportedWorkflowTemplate:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_nodes = payload.get("nodes", [])
    normalized_positions = _normalize_positions(raw_nodes)

    node_by_name = {
        str(node.get("name")): node for node in raw_nodes if node.get("name") is not None
    }
    definition_map: dict[str, ImportedNodeDefinition] = {
        key: value.model_copy(deep=True)
        for key, value in SUPPORTED_NODE_DEFINITIONS.items()
    }
    parsed_nodes: list[ImportedCanvasNode] = []
    edges: list[ImportedCanvasEdge] = []
    incoming_edges: dict[str, list[dict[str, str]]] = defaultdict(list)

    for source_name, connection_types in payload.get("connections", {}).items():
        if not isinstance(connection_types, dict):
            continue
        for connection_type, groups in connection_types.items():
            if not isinstance(groups, list):
                continue
            for group in groups:
                if not isinstance(group, list):
                    continue
                for item in group:
                    target_name = str(item.get("node"))
                    source_node = node_by_name.get(str(source_name))
                    target_node = node_by_name.get(target_name)
                    if not source_node or not target_node:
                        continue
                    edge_id = (
                        f"{source_node.get('id')}-{target_node.get('id')}-{connection_type}"
                    )
                    edges.append(
                        ImportedCanvasEdge(
                            id=edge_id,
                            source=str(source_node.get("id")),
                            target=str(target_node.get("id")),
                            connection_type=str(connection_type),
                        )
                    )
                    incoming_edges[target_name].append(
                        {
                            "source_name": str(source_name),
                            "connection_type": str(connection_type),
                        }
                    )

    form_prefill = copy.deepcopy(DEFAULT_FORM_PREFILL)

    for node in raw_nodes:
        node_id = str(node.get("id"))
        name = str(node.get("name") or "Unnamed Node")
        n8n_type = str(node.get("type") or "")
        parameters = node.get("parameters", {})
        x, y = normalized_positions.get(node_id, (80.0, 80.0))

        supported_type = _detect_supported_type(n8n_type)
        if supported_type:
            definition = definition_map[supported_type]
            type_id = supported_type
        else:
            definition = _build_custom_definition(n8n_type, name)
            definition_map.setdefault(definition.type_id, definition)
            type_id = definition.type_id

        config: dict[str, Any] = {
            "n8nType": n8n_type,
            "parameters": parameters,
        }

        if supported_type == "snowflake":
            query = parameters.get("query")
            if isinstance(query, str) and query.strip():
                form_prefill["sql_query"] = query.strip()
                config["query"] = query.strip()

        if supported_type == "reasoning":
            reasoning_goal = _extract_reasoning_goal(parameters)
            if reasoning_goal:
                form_prefill["reasoning_goal"] = reasoning_goal
                config["reasoning_goal"] = reasoning_goal
            provider, model = _collect_reasoning_model(node, incoming_edges, node_by_name)
            if provider:
                form_prefill["llm"]["provider"] = provider
            if model:
                form_prefill["llm"]["model"] = model

        if supported_type == "gmail":
            email_prefill = _extract_email_prefill(parameters)
            for key, value in email_prefill.items():
                if value:
                    form_prefill["email"][key] = value
            config["email_prefill"] = email_prefill

        parsed_nodes.append(
            ImportedCanvasNode(
                id=node_id,
                type_id=type_id,
                name=name,
                x=x,
                y=y,
                config=config,
            )
        )

    return ImportedWorkflowTemplate(
        id=str(payload.get("id") or path.stem),
        name=str(payload.get("name") or path.stem),
        source_file=path.name,
        executable_nodes=_resolve_executable_order(parsed_nodes),
        node_definitions=list(definition_map.values()),
        nodes=parsed_nodes,
        edges=edges,
        form_prefill=form_prefill,
    )


def load_workflow_templates(base_dir: Path | None = None) -> list[ImportedWorkflowTemplate]:
    root = base_dir or Path(__file__).resolve().parents[1] / "n8n"
    if not root.exists():
        return []

    templates: list[ImportedWorkflowTemplate] = []
    for path in sorted(root.glob("*.json")):
        try:
            templates.append(_parse_workflow_file(path))
        except Exception:
            continue
    return templates

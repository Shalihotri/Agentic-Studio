import { useEffect, useMemo, useRef, useState } from "react";
import { useAuth0 } from "@auth0/auth0-react";
import darkLogo from "../Full Logo_Dark Grey.png";
import lightLogo from "../Full Logo_White.png";

const providerModels = {
  openai: ["gpt-5.4", "gpt-5.4-mini", "gpt-5.2", "gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "o4-mini", "o3", "o1"],
  google: ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
  groq: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "openai/gpt-oss-120b", "openai/gpt-oss-20b"],
};

const baseCatalog = {
  snowflake: { type_id: "snowflake", title: "Snowflake", category: "Tool Setup", subtitle: "Warehouse Query", color: "tool", supported: true },
  chat_model: { type_id: "chat_model", title: "Chat Model", category: "LLM Setup", subtitle: "Provider Model", color: "llm", supported: true },
  memory: { type_id: "memory", title: "Memory", category: "LLM Setup", subtitle: "Session Memory", color: "llm", supported: true },
  output_parser: { type_id: "output_parser", title: "Structured Output Parser", category: "LLM Setup", subtitle: "JSON Schema Parser", color: "llm", supported: true },
  reasoning: { type_id: "reasoning", title: "Reasoning", category: "LLM Setup", subtitle: "Agent Step", color: "llm", supported: true },
  gmail: { type_id: "gmail", title: "Send Email", category: "Action Setup", subtitle: "Gmail Action", color: "action", supported: true },
  outlook: { type_id: "outlook", title: "Send Email", category: "Action Setup", subtitle: "Outlook Action", color: "action", supported: true },
};

const defaultForm = {
  sql_query: "Provide your SQL Query.",
  max_rows: 25,
  snowflake: { role: "", warehouse: "", database: "", schema: "", table: "" },
  reasoning_goal: "Identify the key revenue patterns and write an exec-ready summary.",
  llm: { provider: "groq", model: providerModels.groq[0], api_key: "" },
  memory: { session_key: "default-session" },
  output_parser: { schema: "" },
  email: {
    action: "send",
    to: "",
    cc: "",
    bcc: "",
    subject: "Weekly revenue snapshot",
    instructions: "Keep it concise and call out the top 3 observations.",
    thread_id: "",
    reply_to_message_id: "",
  },
};

const PAGE_SIZE = 50;
const PALETTE = ["#276257", "#ca7b47", "#6b5ee8", "#2a6d8d", "#e8845e", "#1c3d39"];
const NODE_WIDTH = 168;
const NODE_HEIGHT = 84;
const FIT_PADDING = 120;
const AUTH0_ALLOWED_ORIGIN = "https://agentic-studio-five.vercel.app";

function cloneDefaultForm() {
  return JSON.parse(JSON.stringify(defaultForm));
}

function mergeForm(prefill) {
  const next = cloneDefaultForm();
  if (!prefill) return next;
  next.sql_query = prefill.sql_query ?? next.sql_query;
  next.max_rows = prefill.max_rows ?? next.max_rows;
  next.snowflake = { ...next.snowflake, ...(prefill.snowflake || {}) };
  next.reasoning_goal = prefill.reasoning_goal ?? next.reasoning_goal;
  next.llm = { ...next.llm, ...(prefill.llm || {}) };
  next.email = { ...next.email, ...(prefill.email || {}) };
  return next;
}

function getModels(provider, current) {
  const list = providerModels[provider] || providerModels.openai;
  return current && !list.includes(current) ? [current, ...list] : list;
}

function parseEmails(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function parseError(text) {
  try {
    const parsed = JSON.parse(text);
    return parsed.detail || text;
  } catch {
    return text;
  }
}

function buildQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value) search.set(key, value);
  });
  const query = search.toString();
  return query ? `?${query}` : "";
}

function quoteSqlIdentifier(value) {
  return `"${String(value).replace(/"/g, '""')}"`;
}

function formatJsonBlock(value) {
  if (!value) return "";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function groupCatalog(catalog) {
  return Object.values(catalog).reduce((acc, item) => {
    const key = item.category || "Imported Nodes";
    acc[key] = acc[key] || [];
    acc[key].push(item);
    return acc;
  }, {});
}

function ResultsTable({ rows }) {
  const [page, setPage] = useState(0);
  if (!rows?.length) return <p>No rows returned.</p>;
  const columns = Object.keys(rows[0]);
  const totalPages = Math.ceil(rows.length / PAGE_SIZE);
  const pageRows = rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  return (
    <div>
      <div className="table-shell">
        <table className="results-table">
          <thead><tr>{columns.map((col) => <th key={col}>{col}</th>)}</tr></thead>
          <tbody>
            {pageRows.map((row, i) => (
              <tr key={i}>{columns.map((col) => <td key={col}>{String(row[col] ?? "")}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 ? (
        <div className="pagination">
          <button type="button" className="secondary-button page-btn" disabled={page === 0} onClick={() => setPage((p) => Math.max(0, p - 1))}>‹ Prev</button>
          <span className="page-info">Page {page + 1} of {totalPages}</span>
          <button type="button" className="secondary-button page-btn" disabled={page === totalPages - 1} onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}>Next ›</button>
        </div>
      ) : null}
    </div>
  );
}

function FormattedAnalysis({ text }) {
  if (!text) return null;

  const clean = text
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_{2}([^_]+)_{2}/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/[ \t]{2,}/g, " ");

  const lines = clean.split("\n");
  const elements = [];
  let key = 0;

  for (const rawLine of lines) {
    const line = rawLine.trim();

    if (!line) {
      if (elements.length && elements[elements.length - 1].type !== "spacer") {
        elements.push({ type: "spacer", key: key += 1 });
      }
      continue;
    }

    const numbered = line.match(/^(\d+)\.\s+(.+)/);
    if (numbered) {
      elements.push({ type: "numbered", num: numbered[1], text: numbered[2], key: key += 1 });
      continue;
    }

    const bulleted = line.match(/^[-*•▸]\s+(.+)/);
    if (bulleted) {
      elements.push({ type: "bullet", text: bulleted[1], key: key += 1 });
      continue;
    }

    if (line.endsWith(":") && line.length < 80 && !line.includes(".")) {
      elements.push({ type: "subheading", text: line, key: key += 1 });
      continue;
    }

    if (line === line.toUpperCase() && line.length > 3 && line.length < 64) {
      elements.push({ type: "heading", text: line, key: key += 1 });
      continue;
    }

    elements.push({ type: "para", text: line, key: key += 1 });
  }

  return (
    <div className="analysis-body">
      {elements.map((element) => {
        if (element.type === "spacer") return <div key={element.key} className="analysis-spacer" />;
        if (element.type === "heading") return <p key={element.key} className="analysis-heading">{element.text}</p>;
        if (element.type === "subheading") return <p key={element.key} className="analysis-subheading">{element.text}</p>;
        if (element.type === "numbered") {
          return (
            <div key={element.key} className="analysis-numbered">
              <span className="analysis-num">{element.num}</span>
              <span>{element.text}</span>
            </div>
          );
        }
        if (element.type === "bullet") {
          return (
            <div key={element.key} className="analysis-bullet">
              <span className="analysis-bullet-dot">▸</span>
              <span>{element.text}</span>
            </div>
          );
        }
        return <p key={element.key} className="analysis-para">{element.text}</p>;
      })}
    </div>
  );
}

function cleanChatInline(value) {
  return String(value || "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\*([^*]+)\*/g, "$1")
    .replace(/_{2}([^_]+)_{2}/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+--\s+/g, " ")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function FormattedChatMessage({ text }) {
  const lines = String(text || "")
    .replace(/^#{1,6}\s+/gm, "")
    .split("\n");
  const blocks = [];
  let list = null;

  const flushList = () => {
    if (list?.items.length) blocks.push(list);
    list = null;
  };

  lines.forEach((rawLine) => {
    const line = rawLine.trim();

    if (!line || /^-{2,}$/.test(line)) {
      flushList();
      return;
    }

    const numbered = line.match(/^(\d+)[.)]\s+(.+)/);
    if (numbered) {
      if (list?.type !== "ol") flushList();
      list = list || { type: "ol", items: [] };
      list.items.push(cleanChatInline(numbered[2]));
      return;
    }

    const bulleted = line.match(/^[-*•]\s+(.+)/);
    if (bulleted) {
      if (list?.type !== "ul") flushList();
      list = list || { type: "ul", items: [] };
      list.items.push(cleanChatInline(bulleted[1]));
      return;
    }

    flushList();
    blocks.push({ type: "p", text: cleanChatInline(line.replace(/^[-*#]+\s*/, "")) });
  });

  flushList();

  if (!blocks.length) return null;

  return (
    <div className="chat-content">
      {blocks.map((block, index) => {
        if (block.type === "ul") {
          return <ul key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ul>;
        }
        if (block.type === "ol") {
          return <ol key={index}>{block.items.map((item, itemIndex) => <li key={itemIndex}>{item}</li>)}</ol>;
        }
        return <p key={index}>{block.text}</p>;
      })}
    </div>
  );
}

function formatNumber(value) {
  if (value == null || Number.isNaN(Number(value))) return "N/A";
  return new Intl.NumberFormat("en-US").format(Number(value));
}

function formatDuration(value) {
  if (value == null || Number.isNaN(Number(value))) return "N/A";
  if (value < 1000) return `${Math.round(value)} ms`;
  return `${(Number(value) / 1000).toFixed(2)} s`;
}

function formatDateTime(value) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function formatPercent(value) {
  if (value == null || Number.isNaN(Number(value))) return "Pending";
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatCurrency(value) {
  if (value == null || Number.isNaN(Number(value))) return "Pending";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(value));
}

function MonitoringMetricCard({ label, value, hint }) {
  return (
    <div className="monitoring-metric-card">
      <span className="monitoring-metric-label">{label}</span>
      <strong>{value}</strong>
      {hint ? <span className="monitoring-metric-hint">{hint}</span> : null}
    </div>
  );
}

function getClearsEvaluation(monitoring) {
  const { overview, stages = [] } = monitoring;
  const completedStages = stages.filter((stage) => stage.status === "completed").length;
  const failedStages = stages.filter((stage) => stage.status === "error").length;
  const latestLlmOutput = [...stages].reverse().find((stage) => stage.run_type === "llm" && stage.output_preview)?.output_preview;
  const hasOutput = Boolean(latestLlmOutput);
  const hasRows = Number(overview.row_count) > 0;
  const hasStructuredOutput = Boolean(overview.structured_output_available);
  const runtime = Number(overview.total_duration_ms) || 0;

  return [
    {
      key: "correctness",
      label: "Correctness",
      status: hasStructuredOutput || hasRows ? "Review" : "Needs Data",
      score: hasStructuredOutput || hasRows ? 0.7 : 0.35,
      rationale: hasStructuredOutput
        ? "Structured output is available for factual review against expected fields."
        : hasRows
          ? "Rows were returned, but no ground truth is attached for automated correctness scoring."
          : "No returned rows or structured output were available to validate factual accuracy.",
    },
    {
      key: "latency",
      label: "Latency",
      status: runtime <= 10000 ? "Pass" : runtime <= 30000 ? "Review" : "Slow",
      score: runtime <= 10000 ? 1 : runtime <= 30000 ? 0.7 : 0.4,
      rationale: `The workflow completed in ${formatDuration(runtime)}.`,
    },
    {
      key: "execution",
      label: "Execution",
      status: failedStages ? "Fail" : completedStages ? "Pass" : "Needs Data",
      score: failedStages ? 0.2 : completedStages ? 1 : 0.35,
      rationale: failedStages
        ? `${failedStages} stage${failedStages === 1 ? "" : "s"} reported an error.`
        : `${completedStages} stage${completedStages === 1 ? "" : "s"} completed without recorded errors.`,
    },
    {
      key: "adherence",
      label: "Adherence",
      status: hasStructuredOutput ? "Pass" : hasOutput ? "Review" : "Needs Data",
      score: hasStructuredOutput ? 0.9 : hasOutput ? 0.65 : 0.35,
      rationale: hasStructuredOutput
        ? "The LLM response produced structured output that can be checked against the expected contract."
        : hasOutput
          ? "The LLM returned text output, but no structured contract was available for strict format checks."
          : "No LLM output was available for instruction or format adherence checks.",
    },
    {
      key: "relevance",
      label: "Relevance",
      status: hasOutput || hasRows ? "Review" : "Needs Data",
      score: hasOutput || hasRows ? 0.7 : 0.35,
      rationale: hasOutput
        ? "The final LLM output is present and can be compared with the user's request."
        : hasRows
          ? "Query results are available, but no LLM response preview was captured for relevance scoring."
          : "No output was available to compare against the request.",
    },
    {
      key: "safety",
      label: "Safety",
      status: hasOutput ? "Review" : "Needs Data",
      score: hasOutput ? 0.65 : 0.35,
      rationale: hasOutput
        ? "Safety needs an LLM judge or policy scorer; no safety violation was recorded in telemetry."
        : "No LLM output was available for safety review.",
    },
  ];
}

function MonitoringEvaluationCard({ item }) {
  return (
    <article className="monitoring-eval-card">
      <div className="monitoring-eval-head">
        <span className="monitoring-summary-label">{item.label}</span>
        <span className={`pill ${item.status === "Pass" ? "pill-success" : item.status === "Fail" || item.status === "Slow" ? "pill-error" : "pill-muted"}`}>{item.status}</span>
      </div>
      <strong>{formatPercent(item.score)}</strong>
      <p>{item.rationale}</p>
    </article>
  );
}

function MonitoringView({ result }) {
  const monitoring = result?.monitoring;

  if (!monitoring) {
    return <div className="empty-state"><p>Run the workflow to populate monitoring telemetry.</p></div>;
  }

  const { overview, stages } = monitoring;
  const clearsEvaluation = getClearsEvaluation(monitoring);

  return (
    <div className="monitoring-shell">
      <section>
        <div className="analysis-header">
          <div>
            <h3>Workflow BI</h3>
            <p className="analysis-caption">Operational metrics for the full AI workflow: latency, token usage, prompt lineage, and stage-by-stage execution.</p>
          </div>
        </div>
        <div className="monitoring-metric-grid">
          <MonitoringMetricCard label="Total Runtime" value={formatDuration(overview.total_duration_ms)} hint={`${overview.llm_call_count} LLM calls`} />
          <MonitoringMetricCard label="Total Tokens" value={formatNumber(overview.total_tokens)} hint={`${formatNumber(overview.prompt_tokens)} prompt / ${formatNumber(overview.completion_tokens)} completion`} />
          <MonitoringMetricCard label="Rows Processed" value={formatNumber(overview.row_count)} hint={`${formatNumber(overview.chart_count)} charts`} />
          <MonitoringMetricCard label="Tool Stages" value={formatNumber(overview.tool_call_count)} hint={`${formatNumber(stages.length)} recorded stages`} />
        </div>
      </section>

      <section>
        <div className="analysis-header">
          <div>
            <h3>Cost</h3>
            <p className="analysis-caption">Usage and cost view for the current run.</p>
          </div>
        </div>
        <div className="monitoring-metric-grid">
          <MonitoringMetricCard label="Estimated Cost" value={formatCurrency(overview.estimated_cost_usd)} hint="Pending until model pricing is configured" />
          <MonitoringMetricCard label="Prompt Tokens" value={formatNumber(overview.prompt_tokens)} hint="Input usage" />
          <MonitoringMetricCard label="Completion Tokens" value={formatNumber(overview.completion_tokens)} hint="Output usage" />
          <MonitoringMetricCard label="Total Tokens" value={formatNumber(overview.total_tokens)} hint={`${overview.provider} / ${overview.model}`} />
        </div>
      </section>

      <section>
        <div className="analysis-header">
          <div>
            <h3>CLEARS Evaluation</h3>
            <p className="analysis-caption">LLM output is grouped using MLflow's CLEARS dimensions: correctness, latency, execution, adherence, relevance, and safety.</p>
          </div>
        </div>
        <div className="monitoring-eval-grid">
          {clearsEvaluation.map((item) => <MonitoringEvaluationCard key={item.key} item={item} />)}
        </div>
      </section>

      <section>
        <div className="analysis-header">
          <div>
            <h3>Stage Timeline</h3>
            <p className="analysis-caption">Each step captures prompt lineage, execution latency, row volume, and token usage where available.</p>
          </div>
        </div>
        <div className="monitoring-stage-list">
          {stages.map((stage) => (
            <article key={stage.key} className="monitoring-stage-card">
              <div className="monitoring-stage-head">
                <div>
                  <h4>{stage.label}</h4>
                  <p>{stage.provider ? `${stage.provider} / ${stage.model || "default model"}` : stage.run_type || "workflow stage"}</p>
                </div>
                <span className="pill pill-muted">{formatDuration(stage.duration_ms)}</span>
              </div>
              <div className="monitoring-stage-meta">
                <span>Started: {formatDateTime(stage.started_at)}</span>
                <span>Completed: {formatDateTime(stage.completed_at)}</span>
                <span>Rows: {formatNumber(stage.row_count)}</span>
                <span>Tokens: {formatNumber(stage.usage?.total_tokens)}</span>
              </div>
              {stage.prompt_preview ? (
                <div className="monitoring-stage-block">
                  <span className="monitoring-summary-label">Prompt Preview</span>
                  <pre>{stage.prompt_preview}</pre>
                </div>
              ) : null}
              {stage.output_preview ? (
                <div className="monitoring-stage-block">
                  <span className="monitoring-summary-label">Output Preview</span>
                  <pre>{stage.output_preview}</pre>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

import {
  LineChart, BarChart, AreaChart, PieChart,
  Line, Bar, Area, Pie, Cell,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from "recharts";

const SEVERITY_COLORS = { HIGH: "#e74c3c", MEDIUM: "#e67e22", LOW: "#2ecc71" };

/** Normalise a chart spec into a unified shape understood by RechartsChart */
function normaliseSpec(spec) {
  if (!spec) return null;

  // Multi-series spec: { data, x_key, series:[{key,label,color}], chart_type, severity_key? }
  if (Array.isArray(spec.series) && spec.series.length) return spec;

  // Legacy flat spec: { data, x_key, y_key, chart_type }
  if (spec.x_key && spec.y_key) {
    return {
      ...spec,
      series: [{ key: spec.y_key, label: spec.y_key, color: PALETTE[0] }],
    };
  }

  return spec;
}

const CustomDot = ({ cx, cy, payload, severityKey }) => {
  if (!severityKey || !payload) return null;
  const sev = String(payload[severityKey] || "").toUpperCase();
  const fill = SEVERITY_COLORS[sev] || PALETTE[2];
  return <circle cx={cx} cy={cy} r={6} fill={fill} stroke="#fff" strokeWidth={1.5} />;
};

function RechartsChart({ spec }) {
  const norm = normaliseSpec(spec);
  if (!norm?.data?.length || !norm.x_key) {
    return <p style={{ color: "var(--muted)", fontSize: 13 }}>No chart data available.</p>;
  }

  const { data, x_key, series = [], chart_type = "line", severity_key, title } = norm;

  // Clean data – ensure numeric y values
  const clean = data.map((row) => {
    const entry = { ...row, [x_key]: String(row[x_key] ?? "") };
    series.forEach(({ key }) => { entry[key] = isNaN(Number(row[key])) ? 0 : Number(row[key]); });
    return entry;
  });

  const axisStyle = { fontSize: 11, fill: "var(--muted)" };
  const gridStroke = "rgba(166,186,214,0.12)";
  const tooltipStyle = {
    backgroundColor: "var(--panel-2)", border: "1px solid var(--line-strong)",
    borderRadius: 8, fontSize: 12, color: "var(--text)",
  };

  if (chart_type === "pie") {
    const pieData = clean.map((row) => ({ name: row[x_key], value: Number(row[series[0]?.key] ?? 0) }));
    return (
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={110} innerRadius={50} paddingAngle={3} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
            {pieData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
          </Pie>
          <Tooltip contentStyle={tooltipStyle} />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    );
  }

  const ChartComponent = chart_type === "bar" ? BarChart : chart_type === "area" ? AreaChart : LineChart;

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ChartComponent data={clean} margin={{ top: 8, right: 16, left: 0, bottom: 60 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
        <XAxis dataKey={x_key} tick={{ ...axisStyle, angle: -40, textAnchor: "end", dy: 10 }} interval={0} />
        <YAxis tick={axisStyle} width={48} />
        <Tooltip contentStyle={tooltipStyle} />
        {series.length > 1 && <Legend wrapperStyle={{ fontSize: 12, color: "var(--muted)" }} />}
        {series.map(({ key, label, color }, idx) => {
          const stroke = color || PALETTE[idx % PALETTE.length];
          const commonProps = { key, dataKey: key, name: label || key, stroke, strokeWidth: 2, dot: severity_key ? <CustomDot severityKey={severity_key} /> : { r: 4, fill: stroke }, activeDot: { r: 6 } };
          if (chart_type === "bar") return <Bar key={key} dataKey={key} name={label || key} fill={stroke} radius={[3, 3, 0, 0]} />;
          if (chart_type === "area") return <Area key={key} type="monotone" dataKey={key} name={label || key} stroke={stroke} fill={stroke} fillOpacity={0.15} strokeWidth={2} dot={severity_key ? <CustomDot severityKey={severity_key} /> : { r: 4 }} />;
          return <Line key={key} type="monotone" {...commonProps} />;
        })}
      </ChartComponent>
    </ResponsiveContainer>
  );
}

// Keep the old name as an alias so no render-site code needs to change
const PlotlyChart = RechartsChart;

function App() {
  const {
    isLoading: isAuthLoading,
    isAuthenticated,
    error: authError,
    loginWithRedirect,
    logout,
    user,
  } = useAuth0();
  const canvasRef = useRef(null);
  const [theme, setTheme] = useState("dark");
  const [form, setForm] = useState(cloneDefaultForm);
  const [catalog, setCatalog] = useState(baseCatalog);
  const [nodes, setNodes] = useState([]);
  const [edges, setEdges] = useState([]);
  const [selectedNodeId, setSelectedNodeId] = useState(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState(null);
  const [connectingFrom, setConnectingFrom] = useState(null);
  const [canvasOffset, setCanvasOffset] = useState({ x: 0, y: 0 });
  const [canvasScale, setCanvasScale] = useState(1);
  const [pendingFit, setPendingFit] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [workflows, setWorkflows] = useState([]);
  const [activeWorkflowId, setActiveWorkflowId] = useState("");
  const [importNote, setImportNote] = useState("Loading n8n imports...");
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [workspaceSection, setWorkspaceSection] = useState("build");
  const [snowflakeMetadata, setSnowflakeMetadata] = useState({ roles: [], warehouses: [], databases: [], schemas: [], tables: [] });
  const [snowflakeStatus, setSnowflakeStatus] = useState("Loading Snowflake metadata...");

  const selectedNode = useMemo(() => nodes.find((node) => node.id === selectedNodeId) || null, [nodes, selectedNodeId]);
  const selectedDefinition = selectedNode ? catalog[selectedNode.type_id] : null;
  const groupedCatalog = useMemo(() => groupCatalog(catalog), [catalog]);
  const activeWorkflow = useMemo(
    () => workflows.find((workflow) => workflow.id === activeWorkflowId) || null,
    [activeWorkflowId, workflows]
  );
  const companyLogo = theme === "dark" ? lightLogo : darkLogo;
  const workflowLabel = activeWorkflow?.name || "Custom Workflow";
  const workspaceContextLabel = workspaceSection === "monitoring"
    ? "Monitoring"
    : selectedNode?.name || "Build";
  const currentOrigin = typeof window !== "undefined" ? window.location.origin : AUTH0_ALLOWED_ORIGIN;
  const isAllowedOrigin = currentOrigin === AUTH0_ALLOWED_ORIGIN;
  const authStatusLabel = isAuthLoading ? "Checking session" : isAuthenticated ? "Authenticated" : "Guest";
  const executableNodes = useMemo(() => {
    const supportedNodes = nodes.filter((node) => catalog[node.type_id]?.supported);
    if (supportedNodes.length <= 1) {
      return supportedNodes.map((node) => node.type_id);
    }

    const supportedIds = new Set(supportedNodes.map((node) => node.id));
    const supportedEdges = edges.filter((edge) => supportedIds.has(edge.source) && supportedIds.has(edge.target));
    if (!supportedEdges.length) {
      return supportedNodes.map((node) => node.type_id);
    }

    const indegree = new Map(supportedNodes.map((node) => [node.id, 0]));
    const adjacency = new Map(supportedNodes.map((node) => [node.id, []]));
    supportedEdges.forEach((edge) => {
      adjacency.get(edge.source)?.push(edge.target);
      indegree.set(edge.target, (indegree.get(edge.target) || 0) + 1);
    });

    const queue = supportedNodes
      .filter((node) => (indegree.get(node.id) || 0) === 0)
      .sort((a, b) => a.x - b.x || a.y - b.y);
    const orderedIds = [];

    while (queue.length) {
      const current = queue.shift();
      orderedIds.push(current.id);
      (adjacency.get(current.id) || []).forEach((targetId) => {
        indegree.set(targetId, (indegree.get(targetId) || 0) - 1);
        if ((indegree.get(targetId) || 0) === 0) {
          const targetNode = supportedNodes.find((node) => node.id === targetId);
          if (targetNode) queue.push(targetNode);
        }
      });
      queue.sort((a, b) => a.x - b.x || a.y - b.y);
    }

    const resolved = orderedIds.length === supportedNodes.length
      ? orderedIds
      : supportedNodes.map((node) => node.id);
    return resolved
      .map((id) => supportedNodes.find((node) => node.id === id))
      .filter(Boolean)
      .map((node) => node.type_id);
  }, [catalog, edges, nodes]);

  useEffect(() => {
    if (!pendingFit) return;
    fitCanvasToNodes();
    setPendingFit(false);
  }, [nodes, pendingFit]);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  useEffect(() => {
    const element = canvasRef.current;
    if (!element) return undefined;

    function onWheel(event) {
      event.preventDefault();
      event.stopPropagation();
      handleCanvasWheel(event);
    }

    element.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      element.removeEventListener("wheel", onWheel);
    };
  }, [canvasOffset, canvasScale]);

  useEffect(() => {
    let cancelled = false;
    fetch("/workflows/imported")
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Unable to load imported n8n workflows.")))
      .then((items) => {
        if (cancelled) return;
        setWorkflows(items);
        resetToBlankWorkflow(items);
      })
      .catch((err) => !cancelled && setImportNote(err.message));
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const { role, warehouse, database, schema } = form.snowflake;
    setSnowflakeStatus("Loading Snowflake metadata...");
    fetch(`/snowflake/metadata${buildQuery({ role, warehouse, database, schema })}`)
      .then((response) => response.ok ? response.json() : Promise.reject(new Error("Unable to load Snowflake metadata.")))
      .then((metadata) => {
        if (cancelled) return;
        setSnowflakeMetadata({
          roles: metadata.roles || [],
          warehouses: metadata.warehouses || [],
          databases: metadata.databases || [],
          schemas: metadata.schemas || [],
          tables: metadata.tables || [],
        });
        setSnowflakeStatus("Metadata loaded");
      })
      .catch((err) => {
        if (cancelled) return;
        setSnowflakeMetadata({ roles: [], warehouses: [], databases: [], schemas: [], tables: [] });
        setSnowflakeStatus(err.message);
      });
    return () => { cancelled = true; };
  }, [form.snowflake.role, form.snowflake.warehouse, form.snowflake.database, form.snowflake.schema]);

  function resetToBlankWorkflow(all = workflows) {
    setCatalog(baseCatalog);
    setNodes([]);
    setEdges([]);
    setForm(cloneDefaultForm());
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setConnectingFrom(null);
    setActiveWorkflowId("");
    setWorkflows(all);
    setCanvasOffset({ x: 0, y: 0 });
    setCanvasScale(1);
    setResult(null);
    setChatMessages([]);
    setChatInput("");
    setError("");
    setImportNote(
      all.length
        ? "Starting with a blank workflow. You can build your own or import one from the dropdown."
        : "No n8n workflow JSON files found. Starting with a blank workflow."
    );
  }

  function applyWorkflow(template, all = workflows) {
    const nextCatalog = { ...baseCatalog };
    template.node_definitions.forEach((definition) => { nextCatalog[definition.type_id] = definition; });
    setCatalog(nextCatalog);
    setNodes(template.nodes);
    setEdges(template.edges);
    setForm(mergeForm(template.form_prefill));
    setSelectedNodeId(template.nodes[0]?.id || null);
    setSelectedEdgeId(null);
    setConnectingFrom(null);
    setActiveWorkflowId(template.id);
    setWorkflows(all);
    setCanvasOffset({ x: 0, y: 0 });
    setCanvasScale(1);
    setPendingFit(true);
    setResult(null);
    setChatMessages([]);
    setChatInput("");
    setError("");
    setImportNote(`Imported ${template.nodes.length} nodes from ${template.source_file}. Supported nodes were prefilled.`);
  }

  function fitCanvasToNodes() {
    if (!canvasRef.current || !nodes.length) {
      setCanvasOffset({ x: 0, y: 0 });
      setCanvasScale(1);
      return;
    }

    const rect = canvasRef.current.getBoundingClientRect();
    const minX = Math.min(...nodes.map((node) => node.x));
    const minY = Math.min(...nodes.map((node) => node.y));
    const maxX = Math.max(...nodes.map((node) => node.x + NODE_WIDTH));
    const maxY = Math.max(...nodes.map((node) => node.y + NODE_HEIGHT));
    const contentWidth = Math.max(1, maxX - minX);
    const contentHeight = Math.max(1, maxY - minY);
    const nextScale = Math.min(
      1,
      Math.max(
        0.45,
        Math.min(
          (rect.width - FIT_PADDING) / contentWidth,
          (rect.height - FIT_PADDING) / contentHeight
        )
      )
    );

    setCanvasScale(nextScale);
    setCanvasOffset({
      x: (rect.width - contentWidth * nextScale) / 2 - minX * nextScale,
      y: (rect.height - contentHeight * nextScale) / 2 - minY * nextScale,
    });
  }

  function updateField(name, value) {
    setForm((current) => ({ ...current, [name]: value }));
  }

  function updateSnowflakeField(name, value) {
    setForm((current) => {
      const snowflake = { ...current.snowflake, [name]: value };
      if (name === "role") {
        snowflake.warehouse = "";
        snowflake.database = "";
        snowflake.schema = "";
        snowflake.table = "";
      }
      if (name === "database") {
        snowflake.schema = "";
        snowflake.table = "";
      }
      if (name === "schema") {
        snowflake.table = "";
      }
      const next = { ...current, snowflake };
      if (name === "table" && value && current.sql_query === "Provide your SQL Query.") {
        const tableName = [snowflake.database, snowflake.schema, value].filter(Boolean).map(quoteSqlIdentifier).join(".");
        next.sql_query = tableName ? `SELECT * FROM ${tableName} LIMIT ${current.max_rows}` : current.sql_query;
      }
      return next;
    });
  }

  function updateEmailField(name, value) {
    setForm((current) => ({ ...current, email: { ...current.email, [name]: value } }));
  }

  function updateLlmField(name, value) {
    setForm((current) => {
      const llm = { ...current.llm, [name]: value };
      if (name === "provider") llm.model = getModels(value, current.llm.model)[0];
      return { ...current, llm };
    });
  }

  function updateMemoryField(name, value) {
    setForm((current) => ({ ...current, memory: { ...current.memory, [name]: value } }));
  }

  function updateOutputParserField(name, value) {
    setForm((current) => ({ ...current, output_parser: { ...current.output_parser, [name]: value } }));
  }

  function updateSelectedNode(name, value) {
    setNodes((current) => current.map((node) => node.id === selectedNodeId ? { ...node, [name]: value } : node));
  }

  function updateSelectedNodeParameters(rawValue) {
    setNodes((current) => current.map((node) => {
      if (node.id !== selectedNodeId) return node;
      try {
        return { ...node, config: { ...node.config, parameters: JSON.parse(rawValue), rawEditorValue: rawValue } };
      } catch {
        return { ...node, config: { ...node.config, rawEditorValue: rawValue } };
      }
    }));
  }

  function handlePaletteDragStart(event, typeId) {
    event.dataTransfer.setData("application/x-node-type", typeId);
  }

  function createConnection(sourceId, targetId) {
    if (!sourceId || !targetId || sourceId === targetId) {
      setConnectingFrom(null);
      return;
    }
    const nextId = `${sourceId}-${targetId}-main`;
    setEdges((current) => {
      if (current.some((edge) => edge.id === nextId)) {
        return current;
      }
      return [
        ...current,
        { id: nextId, source: sourceId, target: targetId, connection_type: "main" },
      ];
    });
    setConnectingFrom(null);
  }

  function handleOutputHandlePointerDown(event, nodeId) {
    event.preventDefault();
    event.stopPropagation();
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
    setConnectingFrom(nodeId);
  }

  function handleInputHandlePointerDown(event, nodeId) {
    event.preventDefault();
    event.stopPropagation();
    if (connectingFrom) {
      createConnection(connectingFrom, nodeId);
      return;
    }
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
  }

  function handleCanvasDrop(event) {
    event.preventDefault();
    const typeId = event.dataTransfer.getData("application/x-node-type");
    if (!typeId || !canvasRef.current || !catalog[typeId]) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const nextId = `${typeId}-${Date.now()}`;
    setNodes((current) => [...current, {
      id: nextId,
      type_id: typeId,
      name: catalog[typeId].title,
      x: (event.clientX - rect.left - canvasOffset.x) / canvasScale - 84,
      y: (event.clientY - rect.top - canvasOffset.y) / canvasScale - 34,
      config: { parameters: {}, rawEditorValue: "{}" },
    }]);
    setSelectedNodeId(nextId);
  }

  function handleNodePointerDown(event, nodeId) {
    event.preventDefault();
    event.stopPropagation();
    setSelectedNodeId(nodeId);
    setSelectedEdgeId(null);
    const startX = event.clientX;
    const startY = event.clientY;
    const currentNode = nodes.find((node) => node.id === nodeId);
    if (!currentNode) return;
    function onMove(moveEvent) {
      setNodes((current) => current.map((node) => node.id === nodeId ? { ...node, x: currentNode.x + (moveEvent.clientX - startX) / canvasScale, y: currentNode.y + (moveEvent.clientY - startY) / canvasScale } : node));
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function handleBoardPointerDown(event) {
    if (event.target.closest(".dag-node")) return;
    if (event.target.closest(".edge-hitbox")) {
      const edgeId = event.target.dataset.edgeId;
      setSelectedEdgeId(edgeId || null);
      setSelectedNodeId(null);
      setConnectingFrom(null);
      return;
    }
    const startX = event.clientX;
    const startY = event.clientY;
    const startOffset = canvasOffset;
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    setConnectingFrom(null);
    function onMove(moveEvent) {
      setCanvasOffset({ x: startOffset.x + moveEvent.clientX - startX, y: startOffset.y + moveEvent.clientY - startY });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function handleCanvasWheel(event) {
    if (!canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const pointerX = event.clientX - rect.left;
    const pointerY = event.clientY - rect.top;
    const zoomFactor = event.deltaY > 0 ? 0.92 : 1.08;
    const nextScale = Math.min(1.6, Math.max(0.35, canvasScale * zoomFactor));
    const worldX = (pointerX - canvasOffset.x) / canvasScale;
    const worldY = (pointerY - canvasOffset.y) / canvasScale;
    setCanvasScale(nextScale);
    setCanvasOffset({
      x: pointerX - worldX * nextScale,
      y: pointerY - worldY * nextScale,
    });
  }

  async function handleSubmit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setResult(null);
    try {
      if (!executableNodes.length) throw new Error("Add at least one executable node before running the workflow.");
      const response = await fetch("/agent/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workflow_nodes: executableNodes,
          sql_query: form.sql_query,
          max_rows: Number(form.max_rows),
          snowflake: {
            role: form.snowflake.role || null,
            warehouse: form.snowflake.warehouse || null,
            database: form.snowflake.database || null,
            schema: form.snowflake.schema || null,
            table: form.snowflake.table || null,
          },
          reasoning_goal: form.reasoning_goal,
          llm: { provider: form.llm.provider, model: form.llm.model, api_key: form.llm.api_key || undefined },
          memory_session_key: form.memory.session_key || null,
          output_parser_schema: form.output_parser.schema || null,
          email: {
            action: form.email.action,
            to: parseEmails(form.email.to),
            cc: parseEmails(form.email.cc),
            bcc: parseEmails(form.email.bcc),
            subject: form.email.subject || null,
            instructions: form.email.instructions,
            thread_id: form.email.thread_id || null,
            reply_to_message_id: form.email.reply_to_message_id || null,
          },
        }),
      });
      if (!response.ok) throw new Error(parseError(await response.text()));
      const payload = await response.json();
      setResult(payload);
      setChatMessages([
        {
          role: "assistant",
          content: payload.analysis
            ? "Run complete. You can ask follow-up questions about the SQL results, analysis, charts, or structured output."
            : "Run complete. You can ask follow-up questions about the returned results.",
        },
      ]);
      setChatInput("");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleResultChatSubmit(event) {
    event.preventDefault();
    const message = chatInput.trim();
    if (!message || !result?.run_id) return;

    setChatLoading(true);
    setError("");
    setChatMessages((current) => [...current, { role: "user", content: message }]);
    setChatInput("");

    try {
      const response = await fetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: result.run_id,
          message,
          memory_session_key: form.memory.session_key || null,
          llm: {
            provider: form.llm.provider,
            model: form.llm.model,
            api_key: form.llm.api_key || undefined,
          },
        }),
      });
      if (!response.ok) throw new Error(parseError(await response.text()));
      const payload = await response.json();
      setChatMessages((current) => [...current, { role: "assistant", content: payload.answer }]);
    } catch (err) {
      setError(err.message);
      setChatMessages((current) => current.slice(0, -1));
    } finally {
      setChatLoading(false);
    }
  }

  const renderedEdges = useMemo(() => edges.map((edge) => {
    const source = nodes.find((node) => node.id === edge.source);
    const target = nodes.find((node) => node.id === edge.target);
    if (!source || !target) return null;
    const x1 = source.x + NODE_WIDTH;
    const y1 = source.y + NODE_HEIGHT / 2;
    const x2 = target.x;
    const y2 = target.y + NODE_HEIGHT / 2;
    const midX = x1 + (x2 - x1) / 2;
    return {
      ...edge,
      x1,
      y1,
      x2,
      y2,
      path: `M ${x1} ${y1} C ${midX} ${y1}, ${midX} ${y2}, ${x2} ${y2}`,
    };
  }).filter(Boolean), [edges, nodes]);

  const signup = () =>
    loginWithRedirect({ authorizationParams: { screen_hint: "signup" } });

  const login = () => loginWithRedirect();

  const handleLogout = () =>
    logout({ logoutParams: { returnTo: window.location.origin } });

  if (isAuthLoading) {
    return (
      <main className="auth-shell">
        <section className="auth-loading-card">
          <img className="auth-brand-logo" src={companyLogo} alt="Blend" />
          <p className="eyebrow">Blend</p>
          <h1>Checking your session</h1>
          <p className="auth-copy">
            Preparing your workspace and verifying authentication with Auth0.
          </p>
        </section>
      </main>
    );
  }

  if (!isAuthenticated) {
    return (
      <main className="auth-shell">
        <section className="auth-hero">
          <div className="auth-hero-panel auth-hero-brand">
            <div className="auth-brand-stack">
              <img className="auth-brand-logo" src={companyLogo} alt="Blend" />
              <p className="eyebrow">Agentic Studio</p>
              <h1>Autonomous AI workflows for secure enterprise operations.</h1>
              <p className="auth-copy">
                Blend turns data, reasoning, and action into one operating surface for teams that need answers fast.
              </p>
            </div>
            <div className="auth-brand-points">
              <div className="auth-point">
                <span className="auth-point-index">01</span>
                <div>
                  <strong>Compose agent workflows visually</strong>
                  <p>Design execution paths across models, data systems, and delivery channels without leaving the canvas.</p>
                </div>
              </div>
              <div className="auth-point">
                <span className="auth-point-index">02</span>
                <div>
                  <strong>Reason on live business data</strong>
                  <p>Move from SQL results to structured analysis, charts, and follow-up answers in one session.</p>
                </div>
              </div>
              <div className="auth-point">
                <span className="auth-point-index">03</span>
                <div>
                  <strong>Ship outcomes, not just prompts</strong>
                  <p>Draft emails, automate responses, and route actions directly from the same product surface.</p>
                </div>
              </div>
            </div>
          </div>

          <div className="auth-hero-panel auth-hero-access">
            <div className="auth-card-header">
              <p className="eyebrow">Secure Access</p>
              <h2>Sign in</h2>
              <p className="auth-copy">
                Authentication is handled by Auth0 Universal Login. Credentials are entered on the hosted Auth0 page after you continue.
              </p>
            </div>

            <div className="auth-action-stack">
              <button type="button" className="auth-primary-button" onClick={login}>
                Login
              </button>
              <button type="button" className="secondary-button auth-secondary-button" onClick={signup}>
                Create account
              </button>
            </div>

            {/* <div className="auth-detail-list">
              <div className="auth-detail-item">
                <span className="auth-detail-label">Tenant</span>
                <strong>gen-bi.us.auth0.com</strong>
              </div>
              <div className="auth-detail-item">
                <span className="auth-detail-label">App Type</span>
                <strong>Single Page Application</strong>
              </div>
              <div className="auth-detail-item">
                <span className="auth-detail-label">Configured Origin</span>
                <strong>{AUTH0_ALLOWED_ORIGIN}</strong>
              </div>
            </div> */}

            {authError ? <p className="auth-message auth-message-error">Error: {authError.message}</p> : null}
            {!isAllowedOrigin ? (
              <p className="auth-message auth-message-warning">
                Current origin is {currentOrigin}. Local testing will keep failing until `http://localhost:443` is added to Allowed Callback URLs, Allowed Logout URLs, and Allowed Web Origins in Auth0.
              </p>
            ) : null}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="app-topbar">
        <div className="topbar-primary">
          <div className="brand-lockup brand-lockup-compact">
            <img className="brand-logo" src={companyLogo} alt="Company logo" />
            <div>
              <p className="eyebrow">{activeWorkflow ? "Agent Studio" : "Agent Studio"}</p>
              <h1>{workflowLabel}</h1>
            </div>
          </div>
          <nav className="topbar-tabs" aria-label="Workspace sections">
            <button type="button" className={`topbar-tab topbar-tab-button ${workspaceSection === "build" ? "topbar-tab-active" : ""}`} onClick={() => setWorkspaceSection("build")}>Build</button>
            <button type="button" className={`topbar-tab topbar-tab-button ${workspaceSection === "monitoring" ? "topbar-tab-active" : ""}`} onClick={() => setWorkspaceSection("monitoring")}>Monitoring</button>
          </nav>
        </div>
        <div className="topbar-secondary">
          <div className="topbar-stat auth-panel-compact">
            <span className="topbar-stat-label">Auth0</span>
            <strong>{authStatusLabel}</strong>
            <span className="auth-panel-copy auth-panel-copy-compact">{user?.email || user?.name || "user"}</span>
            <div className="auth-panel-actions">
              <button type="button" className="secondary-button auth-logout-button" onClick={handleLogout}>Logout</button>
            </div>
          </div>
          <button
            type="button"
            className="secondary-button theme-toggle"
            onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
          >
            {theme === "dark" ? "Light Theme" : "Dark Theme"}
          </button>
          <div className="topbar-stat">
            <span className="topbar-stat-label">Workflow</span>
            <strong>{workflowLabel}</strong>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-label">Model</span>
            <strong>{form.llm.model}</strong>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-label">Selected</span>
            <strong>{selectedNode?.name || "Canvas"}</strong>
          </div>
          <div className="topbar-stat">
            <span className="topbar-stat-label">Runnable</span>
            <strong>{executableNodes.length}</strong>
          </div>
        </div>
      </header>

      <section className="workspace-strip">
        <div className="workspace-crumbs">
          <span className="workspace-pill">Projects</span>
          <span className="workspace-separator">/</span>
          <span className="workspace-pill">{workflowLabel}</span>
          <span className="workspace-separator">/</span>
          <span className="workspace-pill workspace-pill-active">{workspaceContextLabel}</span>
        </div>
        <p className="workspace-summary">
          Provider: {form.llm.provider} | Model: {form.llm.model} | Theme: {theme} | Auth: {authStatusLabel}
        </p>
      </section>

      <section className="dag-layout dag-layout-enterprise">
        <aside className="left-rail">
          <div className="rail-card rail-card-header">
            <p className="eyebrow">Workflow Import</p>
            {workflows.length ? (
              <div className="sidebar-field">
                <label htmlFor="workflow_template">Imported Workflow</label>
                <select id="workflow_template" value={activeWorkflowId} onChange={(event) => {
                  if (!event.target.value) {
                    resetToBlankWorkflow();
                    return;
                  }
                  const next = workflows.find((workflow) => workflow.id === event.target.value);
                  if (next) applyWorkflow(next);
                }}>
                  <option value="">No import (blank workflow)</option>
                  {workflows.map((workflow) => <option key={workflow.id} value={workflow.id}>{workflow.name}</option>)}
                </select>
              </div>
            ) : null}
            <p className="import-note">{importNote}</p>
          </div>

          <div className="rail-card">
            <p className="eyebrow">LLM Setup</p>
            <div className="sidebar-field"><label htmlFor="provider">Provider</label><select id="provider" value={form.llm.provider} onChange={(event) => updateLlmField("provider", event.target.value)}><option value="openai">OpenAI</option><option value="google">Google</option><option value="groq">Groq</option></select></div>
            <div className="sidebar-field"><label htmlFor="model">Model</label><select id="model" value={form.llm.model} onChange={(event) => updateLlmField("model", event.target.value)}>{getModels(form.llm.provider, form.llm.model).map((model) => <option key={model} value={model}>{model}</option>)}</select></div>
            <div className="sidebar-field"><label htmlFor="llm_api_key">API Key</label><input id="llm_api_key" className="sidebar-text-input" type="password" value={form.llm.api_key || ""} onChange={(event) => updateLlmField("api_key", event.target.value)} /></div>
          </div>

          {Object.entries(groupedCatalog).map(([category, defs]) => (
            <div key={category} className="rail-card">
              <p className="eyebrow">{category}</p>
              {defs.map((definition) => (
                <div key={definition.type_id} className={`palette-chip palette-chip-${definition.color || "imported"}`} draggable onDragStart={(event) => handlePaletteDragStart(event, definition.type_id)}>
                  <span>{definition.supported ? "Node" : "Imported"}</span>
                  <strong>{definition.title}</strong>
                  <small>{definition.subtitle}</small>
                </div>
              ))}
            </div>
          ))}
        </aside>

        <form className="canvas-panel canvas-panel-enterprise" onSubmit={handleSubmit}>
          <div className="canvas-header">
            <div>
              <p className="eyebrow">Workflow Canvas</p>
              <h2>Visual Builder</h2>
              <p className="panel-subtitle">Explicit node connections control execution order. Drag to reposition, pan, zoom, or fit the workspace.</p>
            </div>
            <div className="canvas-actions">
              {connectingFrom ? <span className="zoom-indicator">Connecting...</span> : null}
              <span className="zoom-indicator">{Math.round(canvasScale * 100)}%</span>
              {selectedEdgeId ? (
                <button
                  type="button"
                  className="secondary-button delete-button"
                  onClick={() => {
                    setEdges((current) => current.filter((edge) => edge.id !== selectedEdgeId));
                    setSelectedEdgeId(null);
                  }}
                >
                  Delete Arrow
                </button>
              ) : null}
              <button type="button" className="secondary-button" onClick={fitCanvasToNodes}>Fit All</button>
              <button type="button" className="secondary-button" onClick={() => { setCanvasOffset({ x: 0, y: 0 }); setCanvasScale(1); }}>Reset View</button>
              <button type="submit" disabled={loading}>{loading ? "Running..." : "Run Workflow"}</button>
            </div>
          </div>

          <div className="workspace-toolbar">
            <span className="workspace-chip">Interactive Canvas</span>
            <span className="workspace-chip workspace-chip-muted">{selectedNode ? `Selected: ${selectedNode.name}` : "No node selected"}</span>
            <span className="workspace-chip workspace-chip-muted">{selectedEdgeId ? "Arrow selected" : "Arrow-free selection"}</span>
          </div>

          <div ref={canvasRef} className="canvas-board" onDrop={handleCanvasDrop} onDragOver={(event) => event.preventDefault()} onPointerDown={handleBoardPointerDown}>
            <div className="canvas-world" style={{ transform: `translate(${canvasOffset.x}px, ${canvasOffset.y}px) scale(${canvasScale})` }}>
              {!nodes.length ? <div className="canvas-empty"><p>Imported nodes will appear here.</p><p>Drag any node from the left rail to add more.</p></div> : null}
              <svg className="edge-layer" aria-hidden="true">
                <defs>
                  <marker id="edge-arrow" markerWidth="10" markerHeight="10" refX="8" refY="5" orient="auto" markerUnits="strokeWidth">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="rgba(39, 98, 87, 0.55)" />
                  </marker>
                </defs>
                {renderedEdges.map((edge) => (
                  <g key={edge.id}>
                    <path
                      d={edge.path}
                      className={`edge-curve ${selectedEdgeId === edge.id ? "edge-curve-active" : ""}`}
                      markerEnd="url(#edge-arrow)"
                    />
                    <path
                      d={edge.path}
                      className="edge-hitbox"
                      data-edge-id={edge.id}
                    />
                  </g>
                ))}
              </svg>
              {nodes.map((node) => {
                const definition = catalog[node.type_id];
                if (!definition) return null;
                return (
                  <div key={node.id} className={`dag-node dag-node-${definition.color || "imported"} ${selectedNodeId === node.id ? "dag-node-active" : ""}`} style={{ left: node.x, top: node.y }} onPointerDown={(event) => handleNodePointerDown(event, node.id)}>
                    <button type="button" className={`node-handle node-handle-in ${connectingFrom ? "node-handle-ready" : ""}`} onPointerDown={(event) => handleInputHandlePointerDown(event, node.id)} aria-label={`Connect into ${node.name || definition.title}`} />
                    <button type="button" className={`node-handle node-handle-out ${connectingFrom === node.id ? "node-handle-active" : ""}`} onPointerDown={(event) => handleOutputHandlePointerDown(event, node.id)} aria-label={`Connect from ${node.name || definition.title}`} />
                    <span className="node-kicker">{definition.category}</span>
                    <strong>{node.name || definition.title}</strong>
                    <span>{definition.subtitle}</span>
                    {!definition.supported ? <em className="node-badge">Imported only</em> : null}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="canvas-inspector canvas-inspector-enterprise">
            <div className="inspector-head">
              <div>
                <p className="eyebrow">Node Configuration</p>
                <h3>{selectedNode ? (selectedNode.name || selectedDefinition?.title) : "Select a Node"}</h3>
                <p className="panel-subtitle">Inspect imported metadata or adjust runnable node parameters before execution.</p>
              </div>
              {selectedNode ? <button type="button" className="secondary-button delete-button" onClick={() => {
                setNodes((current) => current.filter((node) => node.id !== selectedNodeId));
                setEdges((current) => current.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId));
                setSelectedNodeId(null);
              }}>Delete Node</button> : null}
            </div>

            {selectedNode ? <div className="field field-wide"><label htmlFor="node_name">Node Label</label><input id="node_name" value={selectedNode.name} onChange={(event) => updateSelectedNode("name", event.target.value)} /></div> : null}

            {selectedNode?.type_id === "snowflake" ? (
              <div className="inspector-grid">
                <div className="field"><label htmlFor="snowflake_role">Role</label><select id="snowflake_role" value={form.snowflake.role} onChange={(event) => updateSnowflakeField("role", event.target.value)}><option value="">Default role</option>{snowflakeMetadata.roles.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
                <div className="field"><label htmlFor="snowflake_warehouse">Warehouse</label><select id="snowflake_warehouse" value={form.snowflake.warehouse} onChange={(event) => updateSnowflakeField("warehouse", event.target.value)}><option value="">Default warehouse</option>{snowflakeMetadata.warehouses.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
                <div className="field"><label htmlFor="snowflake_database">Database</label><select id="snowflake_database" value={form.snowflake.database} onChange={(event) => updateSnowflakeField("database", event.target.value)}><option value="">Select database</option>{snowflakeMetadata.databases.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
                <div className="field"><label htmlFor="snowflake_schema">Schema</label><select id="snowflake_schema" value={form.snowflake.schema} onChange={(event) => updateSnowflakeField("schema", event.target.value)} disabled={!form.snowflake.database}><option value="">Select schema</option>{snowflakeMetadata.schemas.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
                <div className="field"><label htmlFor="snowflake_table">Table</label><select id="snowflake_table" value={form.snowflake.table} onChange={(event) => updateSnowflakeField("table", event.target.value)} disabled={!form.snowflake.schema}><option value="">Select table</option>{snowflakeMetadata.tables.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
                <p className="field-hint field-wide">{snowflakeStatus}</p>
                <div className="field field-wide"><label htmlFor="sql_query">SQL Query</label><textarea id="sql_query" rows="8" value={form.sql_query} onChange={(event) => updateField("sql_query", event.target.value)} /></div>
                <div className="field"><label htmlFor="max_rows">Max Rows</label><input id="max_rows" type="number" min="1" max="1000" value={form.max_rows} onChange={(event) => updateField("max_rows", event.target.value)} /></div>
              </div>
            ) : null}

            {selectedNode?.type_id === "reasoning" ? <div className="field field-wide"><label htmlFor="reasoning_goal">Reasoning Goal</label><textarea id="reasoning_goal" rows="10" value={form.reasoning_goal} onChange={(event) => updateField("reasoning_goal", event.target.value)} /></div> : null}

            {selectedNode?.type_id === "chat_model" ? (
              <div className="inspector-grid">
                <div className="field"><label htmlFor="chat_provider">Provider</label><select id="chat_provider" value={form.llm.provider} onChange={(event) => updateLlmField("provider", event.target.value)}><option value="openai">OpenAI</option><option value="google">Google</option><option value="groq">Groq</option></select></div>
                <div className="field"><label htmlFor="chat_model">Model</label><select id="chat_model" value={form.llm.model} onChange={(event) => updateLlmField("model", event.target.value)}>{getModels(form.llm.provider, form.llm.model).map((model) => <option key={model} value={model}>{model}</option>)}</select></div>
              </div>
            ) : null}

            {selectedNode?.type_id === "memory" ? (
              <div className="field field-wide"><label htmlFor="memory_session_key">Session Key</label><input id="memory_session_key" value={form.memory.session_key} onChange={(event) => updateMemoryField("session_key", event.target.value)} /></div>
            ) : null}

            {selectedNode?.type_id === "output_parser" ? (
              <div className="field field-wide"><label htmlFor="output_parser_schema">JSON Schema</label><textarea id="output_parser_schema" rows="14" value={form.output_parser.schema} onChange={(event) => updateOutputParserField("schema", event.target.value)} /></div>
            ) : null}

            {selectedNode && ["gmail", "outlook"].includes(selectedNode.type_id) ? (
              <div className="inspector-grid">
                <div className="field"><label htmlFor="email_action">Action</label><select id="email_action" value={form.email.action} onChange={(event) => updateEmailField("action", event.target.value)}><option value="send">Send</option><option value="draft">Draft</option><option value="reply">Reply</option></select></div>
                <div className="field"><label htmlFor="to">To</label><input id="to" value={form.email.to} onChange={(event) => updateEmailField("to", event.target.value)} /></div>
                <div className="field"><label htmlFor="cc">CC</label><input id="cc" value={form.email.cc} onChange={(event) => updateEmailField("cc", event.target.value)} /></div>
                <div className="field"><label htmlFor="bcc">BCC</label><input id="bcc" value={form.email.bcc} onChange={(event) => updateEmailField("bcc", event.target.value)} /></div>
                <div className="field field-wide"><label htmlFor="subject">Subject</label><input id="subject" value={form.email.subject} onChange={(event) => updateEmailField("subject", event.target.value)} /></div>
                <div className="field field-wide"><label htmlFor="instructions">Email Instructions</label><textarea id="instructions" rows="5" value={form.email.instructions} onChange={(event) => updateEmailField("instructions", event.target.value)} /></div>
                <div className="field"><label htmlFor="thread_id">Thread ID</label><input id="thread_id" value={form.email.thread_id} onChange={(event) => updateEmailField("thread_id", event.target.value)} /></div>
                <div className="field"><label htmlFor="reply_to_message_id">Reply To Message ID</label><input id="reply_to_message_id" value={form.email.reply_to_message_id} onChange={(event) => updateEmailField("reply_to_message_id", event.target.value)} /></div>
              </div>
            ) : null}

            {selectedNode && !selectedDefinition?.supported ? (
              <div className="inspector-grid">
                <div className="field field-wide"><label htmlFor="custom_type">Imported n8n Type</label><input id="custom_type" value={selectedNode.config?.n8nType || selectedDefinition?.origin_type || ""} readOnly /></div>
                <div className="field field-wide"><label htmlFor="custom_parameters">Parameters JSON</label><textarea id="custom_parameters" rows="14" value={selectedNode.config?.rawEditorValue ?? JSON.stringify(selectedNode.config?.parameters || {}, null, 2)} onChange={(event) => updateSelectedNodeParameters(event.target.value)} /></div>
              </div>
            ) : null}

            {!selectedNode ? <div className="inspector-empty"><p>Select a node to edit its imported or executable configuration.</p></div> : null}
            <div className="inspector-summary"><span className="pill">{executableNodes.length} executable nodes</span><span className="pill pill-muted">{nodes.length} total nodes</span></div>
            {error ? <p className="status error">{error}</p> : null}
          </div>
        </form>

        <aside className="results-panel">
          <div className="results-card results-card-enterprise">
            <div className="results-header">
              <div>
                <p className="eyebrow">{workspaceSection === "monitoring" ? "Monitoring" : "Output"}</p>
                <h2>{workspaceSection === "monitoring" ? "Workflow Monitoring" : "Execution Results"}</h2>
                <p className="panel-subtitle">
                  {workspaceSection === "monitoring"
                    ? "LangSmith-oriented telemetry for prompts, tokens, latency, tool spans, and evaluation readiness."
                    : "Query output, reasoning summaries, charts, and delivery details are rendered here."}
                </p>
              </div>
              <span className="pill">{workspaceSection === "monitoring" ? (result?.monitoring ? "Telemetry Ready" : "Waiting") : (result ? `${result.row_count} rows processed` : "Waiting")}</span>
            </div>
            <div className="results-body">
              {workspaceSection === "monitoring" ? (
                <MonitoringView result={result} />
              ) : result ? (
                <>
                  {result.executed_nodes?.includes("snowflake") ? <section><h3>SQL Results</h3><ResultsTable rows={result.sample_rows} /></section> : null}
                  {result.executed_nodes?.includes("reasoning") && result.analysis ? (
                    <section>
                      <div className="analysis-header">
                        <div>
                          <h3>LLM Analysis</h3>
                          <p className="analysis-caption">Structured findings generated from the imported workflow context and query output.</p>
                        </div>
                        <span className="pill pill-llm">Reasoning Complete</span>
                      </div>
                      <div className="analysis-shell">
                        <FormattedAnalysis text={result.analysis} />
                      </div>
                    </section>
                  ) : null}
                  {result.structured_output ? (
                    <section>
                      <h3>Structured Output</h3>
                      <pre>{formatJsonBlock(result.structured_output)}</pre>
                    </section>
                  ) : null}
                  {result.executed_nodes?.includes("reasoning") && result.charts?.length ? (
                    <section>
                      <div className="analysis-header">
                        <div>
                          <h3>Visual Analysis</h3>
                          <p className="analysis-caption">Charts generated from query results. Multi-series and severity-coded dots are supported.</p>
                        </div>
                        {result.charts.some((s) => s.severity_key) && (
                          <div className="severity-legend">
                            <span style={{ color: "#e74c3c" }}>● HIGH</span>
                            <span style={{ color: "#e67e22" }}>● MEDIUM</span>
                            <span style={{ color: "#2ecc71" }}>● LOW</span>
                          </div>
                        )}
                      </div>
                      <div className="charts-grid">
                        {result.charts.map((spec, index) => (
                          <div key={index} className="chart-card">
                            <p className="chart-title">{spec.title}</p>
                            <PlotlyChart spec={spec} />
                          </div>
                        ))}
                      </div>
                    </section>
                  ) : null}
                  {result.executed_nodes?.some((node) => ["gmail", "outlook"].includes(node)) && result.email_result ? (
                    <>
                      <section><h3>Email Draft</h3><div className="email-subject-row"><span className="subject-label">Subject</span><span className="subject-text">{result.generated_subject}</span></div><pre>{result.generated_body}</pre></section>
                      <section><h3>Delivery</h3><div className="delivery-grid">{Object.entries(result.email_result).map(([key, value]) => value != null ? <div key={key} className="delivery-item"><div className="delivery-label">{key.replace(/_/g, " ")}</div><div className="delivery-value">{String(value)}</div></div> : null)}</div></section>
                    </>
                  ) : null}
                  <section>
                    <div className="analysis-header">
                      <div>
                        <h3>Chat On Results</h3>
                        <p className="analysis-caption">Ask follow-up questions about this run using the current model and session memory.</p>
                      </div>
                    </div>
                    <div className="chat-shell">
                      <div className="chat-thread">
                        {chatMessages.length ? chatMessages.map((message, index) => (
                          <div key={`${message.role}-${index}`} className={`chat-bubble chat-bubble-${message.role}`}>
                            <span className="chat-role">{message.role === "assistant" ? "Assistant" : "You"}</span>
                            <FormattedChatMessage text={message.content} />
                          </div>
                        )) : <p className="chat-empty">Run the workflow, then ask follow-up questions here.</p>}
                      </div>
                      <form className="chat-form" onSubmit={handleResultChatSubmit}>
                        <textarea rows="3" value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="Ask about the analysis, rows, charts, or structured output..." />
                        <button type="submit" disabled={chatLoading || !result?.run_id}>{chatLoading ? "Thinking..." : "Send"}</button>
                      </form>
                    </div>
                  </section>
                </>
              ) : <div className="empty-state"><p>Execution output will appear here after the workflow runs.</p></div>}
            </div>
          </div>
        </aside>
      </section>
    </main>
  );
}

export default App;

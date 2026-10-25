import { useQueryClient } from "@tanstack/react-query";
import { Linkedin, RefreshCw } from "lucide-react";

import { DataTable } from "../components/DataTable";
import { Logo } from "../components/Layout";
import { RunForecastButton } from "../components/RunControls";
import { Badge, Card, PageHeader } from "../components/ui";
import { useGet } from "../hooks/useApi";
import { BRAND } from "../lib/branding";

interface Meta {
  app: string;
  version: string;
  tagline: string;
  database: string;
  db_path: string;
  horizons: number[];
  ai: { enabled: boolean; available: boolean; url: string; model: string; models: string[]; reason?: string };
  models: {
    name: string;
    family: string;
    description: string;
    min_obs: number;
    uses_drivers: boolean;
    version: string;
  }[];
}

export default function Settings() {
  const qc = useQueryClient();
  const { data } = useGet<Meta>("/api/meta");
  const { data: catalog } = useGet<{
    metrics: Record<string, { label: string; description: string; format: string }>;
    dimensions: Record<string, { label: string }>;
  }>("/api/semantic/catalog");
  return (
    <div>
      <PageHeader
        eyebrow="Settings"
        title="Settings & About"
        subtitle="Environment, local AI, model catalog and semantic layer."
        actions={<RunForecastButton />}
      />
      <div className="grid gap-5 xl:grid-cols-3">
        <Card title="Local AI (Ollama)">
          <div className="flex items-center gap-2">
            <Badge
              className={data?.ai.available ? "bg-emerald-50 text-emerald-800" : "bg-amber-50 text-amber-800"}
            >
              {data?.ai.available ? "Connected" : "Not connected"}
            </Badge>
            <button
              type="button"
              className="btn-ghost px-2 py-1 text-xs"
              onClick={() => qc.invalidateQueries({ queryKey: ["/api/meta"] })}
            >
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
          <dl className="mt-3 space-y-1.5 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted">URL</dt>
              <dd className="font-mono text-xs">{data?.ai.url}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Model</dt>
              <dd className="font-mono text-xs">{data?.ai.model}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted">Pulled models</dt>
              <dd className="text-xs">{data?.ai.models.join(", ") || "—"}</dd>
            </div>
          </dl>
          {!data?.ai.available && (
            <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-ink-2">
              {data?.ai.reason}. Install Ollama and run{" "}
              <code className="font-mono">ollama pull {data?.ai.model}</code> (or use{" "}
              <code className="font-mono">docker compose up</code>, which starts it). Without it, the analyst
              answers with the deterministic narrative engine.
            </div>
          )}
        </Card>
        <Card title="Environment">
          <dl className="space-y-1.5 text-sm">
            {[
              ["Application", `${data?.app ?? "ForecastLab"} ${data?.version ?? ""}`],
              ["Database", data?.database],
              ["DB file", data?.db_path],
              ["Forecast horizons", data?.horizons.join(", ") + " months"],
              ["Backtesting", "Rolling origin, expanding window"],
              ["Reconciliation", "Bottom-up (Top-down available; MinT on roadmap)"],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="shrink-0 text-muted">{k}</dt>
                <dd className="truncate text-right font-mono text-xs" title={String(v)}>
                  {v}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
        <Card title="About">
          <Logo />
          <p className="mt-2 text-sm text-muted">{BRAND.tagline}</p>
          <div className="mt-4 rounded-lg border border-line p-3 text-sm">
            <div className="font-semibold">{BRAND.signatureEn}</div>
            <div className="text-xs text-muted">{BRAND.titleEn}</div>
            <div className="mt-2 font-semibold">{BRAND.signaturePt}</div>
            <div className="text-xs text-muted">{BRAND.titlePt}</div>
            <a
              href={BRAND.linkedin}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-xs text-brand hover:underline"
            >
              <Linkedin size={12} /> {BRAND.linkedinLabel}
            </a>
          </div>
          <p className="mt-3 text-xs text-muted">
            All demo data is synthetic and fictitious. No paid API, SaaS or cloud service is required.
          </p>
        </Card>
      </div>
      <Card
        className="mt-5"
        title="Model catalog"
        subtitle="Routed per series type by the Model Candidate Router"
      >
        <DataTable
          rows={data?.models ?? []}
          rowKey={(r) => r.name}
          columns={[
            { key: "name", label: "Model", render: (r) => <span className="font-medium">{r.name}</span> },
            { key: "family", label: "Family" },
            {
              key: "description",
              label: "Description",
              render: (r) => <span className="wrap text-xs text-ink-2">{r.description}</span>,
            },
            { key: "min_obs", label: "Min. history", align: "right", render: (r) => `${r.min_obs} m` },
            { key: "uses_drivers", label: "Drivers", render: (r) => (r.uses_drivers ? "yes" : "—") },
            {
              key: "version",
              label: "Version",
              render: (r) => <span className="font-mono text-xs">{r.version}</span>,
            },
          ]}
        />
      </Card>
      <Card
        className="mt-5"
        title="Semantic layer"
        subtitle="Governed metrics and dimensions the AI Analyst can query"
      >
        <DataTable
          rows={Object.entries(catalog?.metrics ?? {}).map(([k, v]) => ({ key: k, ...v }))}
          rowKey={(r) => r.key}
          columns={[
            {
              key: "key",
              label: "Metric",
              render: (r) => <span className="font-mono text-xs">{r.key}</span>,
            },
            { key: "label", label: "Label" },
            {
              key: "description",
              label: "Definition",
              render: (r) => <span className="wrap text-xs text-ink-2">{r.description}</span>,
            },
            { key: "format", label: "Format" },
          ]}
        />
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.keys(catalog?.dimensions ?? {}).map((d) => (
            <Badge key={d} className="bg-blue-50 font-mono text-blue-800">
              {d}
            </Badge>
          ))}
        </div>
      </Card>
    </div>
  );
}

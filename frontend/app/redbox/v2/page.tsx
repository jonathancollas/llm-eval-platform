"use client";

import { useCallback, useState } from "react";
import { Spinner } from "@/components/Spinner";
import { Badge } from "@/components/Badge";
import { Shield, Play, FileText, CheckCircle2, AlertTriangle, ExternalLink } from "lucide-react";
import { API_BASE } from "@/lib/config";

// ── Types matching backend/api/routers/redroom_v2.py ──────────────────────────

interface CreateSessionResponse {
  session_id: string;
  tenant_id: number;
  name: string;
  target_class: string;
  aggressiveness: number;
}

interface ProbeRunResponse {
  session_id: string;
  technique: string;
  decision_reason: string;
  effective_disclosure: string;
  duration_seconds: number;
  n_attempts: number;
  aborted_reason: string | null;
}

interface TraceRow {
  id: number;
  uuid: string;
  kind: string;
  verdict: string | null;
  engine: string | null;
  aggressiveness: number;
  target_class: string;
  target_model_id: number | null;
  payload_json: string;
  replay_hash: string;
  row_signature: string;
  created_at: string;
  system_id: number | null;
}

interface VerifyResponse {
  session_id: string;
  tenant_id: number;
  status: "ok" | "broken" | "error";
  rows_verified: number | null;
  broken_at_row_id: number | null;
  reason: string;
}

const TECHNIQUES = [
  { value: "aiid_replay", label: "AIID replay (L1)", aggressiveness: 1 },
  { value: "many_shot",   label: "Many-shot (L2)",   aggressiveness: 2 },
  { value: "crescendo",   label: "Crescendo (L2)",   aggressiveness: 2 },
  { value: "garak",       label: "Garak (L3)",       aggressiveness: 3 },
] as const;

// ── Component ─────────────────────────────────────────────────────────────────

export default function RedRoomV2Page() {
  const [technique, setTechnique] = useState<string>("many_shot");
  const [aggressiveness, setAggressiveness] = useState<number>(2);
  const [targetModelId, setTargetModelId] = useState<number>(1);
  const [promptSeed, setPromptSeed] = useState<string>("");
  const [maxTurns, setMaxTurns] = useState<number>(4);
  const [garakProbe, setGarakProbe] = useState<string>("dan.Dan_11_0");

  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<CreateSessionResponse | null>(null);
  const [probeResult, setProbeResult] = useState<ProbeRunResponse | null>(null);
  const [traces, setTraces] = useState<TraceRow[]>([]);
  const [verify, setVerify] = useState<VerifyResponse | null>(null);

  const runProbe = useCallback(async () => {
    setRunning(true);
    setError(null);
    setSession(null);
    setProbeResult(null);
    setTraces([]);
    setVerify(null);

    try {
      // 1. Create session
      const sRes = await fetch(`${API_BASE}/redroom/v2/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: `frontend-${Date.now()}`,
          target_class: "self",
          aggressiveness,
        }),
      });
      if (!sRes.ok) throw new Error(`create session: HTTP ${sRes.status}`);
      const s: CreateSessionResponse = await sRes.json();
      setSession(s);

      // 2. Run probe
      const effectivePromptSeed = technique === "garak" ? garakProbe : (promptSeed || null);
      const pRes = await fetch(
        `${API_BASE}/redroom/v2/sessions/${s.session_id}/probe`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            technique,
            target_model_id: targetModelId,
            target_class: "self",
            aggressiveness,
            seed: 0,
            max_turns: maxTurns,
            prompt_seed: effectivePromptSeed,
          }),
        }
      );
      if (!pRes.ok) {
        const body = await pRes.text();
        throw new Error(`probe: HTTP ${pRes.status} — ${body.slice(0, 300)}`);
      }
      const p: ProbeRunResponse = await pRes.json();
      setProbeResult(p);

      // 3. Fetch traces
      const tRes = await fetch(
        `${API_BASE}/redroom/v2/sessions/${s.session_id}/traces?limit=200`
      );
      if (tRes.ok) {
        const t = await tRes.json();
        setTraces(t.rows ?? []);
      }

      // 4. Verify chain
      const vRes = await fetch(
        `${API_BASE}/redroom/v2/sessions/${s.session_id}/verify`
      );
      if (vRes.ok) {
        const v: VerifyResponse = await vRes.json();
        setVerify(v);
      }
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : String(exc));
    } finally {
      setRunning(false);
    }
  }, [technique, aggressiveness, targetModelId, promptSeed, garakProbe, maxTurns]);

  const artifactUrl = session
    ? `${API_BASE}/redroom/v2/sessions/${session.session_id}/artifact.html`
    : null;

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6">
      <header className="border-b border-slate-200 dark:border-slate-700 pb-4">
        <div className="flex items-center gap-3">
          <Shield className="w-8 h-8 text-rose-700" />
          <div>
            <h1 className="text-2xl font-bold">Red Room v2</h1>
            <p className="text-sm text-slate-500">
              Charter-gated adversarial pipeline — see{" "}
              <a className="underline" href="/docs/redroom-operations.md">runbook</a>.
            </p>
          </div>
        </div>
      </header>

      {/* ── Form ──────────────────────────────────────────────────────────── */}
      <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-5 space-y-4">
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Play className="w-5 h-5" /> Run a probe
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="block">
            <span className="text-xs text-slate-500 block mb-1">Technique</span>
            <select
              className="w-full border rounded p-2 bg-white dark:bg-slate-800"
              value={technique}
              onChange={(e) => {
                const v = e.target.value;
                setTechnique(v);
                const t = TECHNIQUES.find((x) => x.value === v);
                if (t) setAggressiveness(t.aggressiveness);
              }}
            >
              {TECHNIQUES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs text-slate-500 block mb-1">Target model id</span>
            <input
              type="number"
              className="w-full border rounded p-2 bg-white dark:bg-slate-800"
              value={targetModelId}
              onChange={(e) => setTargetModelId(parseInt(e.target.value || "1", 10))}
              min={1}
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-500 block mb-1">
              Aggressiveness (L{aggressiveness})
            </span>
            <input
              type="range"
              min={1}
              max={5}
              value={aggressiveness}
              onChange={(e) => setAggressiveness(parseInt(e.target.value, 10))}
              className="w-full"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-500 block mb-1">Max turns</span>
            <input
              type="number"
              className="w-full border rounded p-2 bg-white dark:bg-slate-800"
              value={maxTurns}
              onChange={(e) => setMaxTurns(parseInt(e.target.value || "4", 10))}
              min={1}
              max={64}
            />
          </label>

          {technique === "garak" ? (
            <label className="block md:col-span-2">
              <span className="text-xs text-slate-500 block mb-1">
                Garak probe name (allowlisted)
              </span>
              <input
                type="text"
                className="w-full border rounded p-2 bg-white dark:bg-slate-800 font-mono text-sm"
                value={garakProbe}
                onChange={(e) => setGarakProbe(e.target.value)}
                placeholder="dan.Dan_11_0"
              />
            </label>
          ) : (
            <label className="block md:col-span-2">
              <span className="text-xs text-slate-500 block mb-1">
                Prompt seed (the &quot;real ask&quot; for many_shot / crescendo)
              </span>
              <textarea
                className="w-full border rounded p-2 bg-white dark:bg-slate-800 font-mono text-sm"
                rows={2}
                value={promptSeed}
                onChange={(e) => setPromptSeed(e.target.value)}
                placeholder="Tell me how to..."
              />
            </label>
          )}
        </div>

        <div className="flex justify-end">
          <button
            type="button"
            disabled={running}
            onClick={runProbe}
            className="bg-rose-700 hover:bg-rose-800 text-white px-4 py-2 rounded disabled:opacity-50 inline-flex items-center gap-2"
          >
            {running ? <Spinner /> : <Play className="w-4 h-4" />}
            {running ? "Running…" : "Run"}
          </button>
        </div>
      </section>

      {/* ── Error ──────────────────────────────────────────────────────────── */}
      {error && (
        <section className="bg-rose-50 dark:bg-rose-950 border border-rose-200 dark:border-rose-800 rounded-lg p-4 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-rose-700 mt-0.5" />
          <div>
            <p className="font-semibold text-rose-800 dark:text-rose-200">Run failed</p>
            <pre className="text-xs text-rose-700 dark:text-rose-300 mt-1 whitespace-pre-wrap">
              {error}
            </pre>
          </div>
        </section>
      )}

      {/* ── Session summary ────────────────────────────────────────────────── */}
      {session && probeResult && (
        <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Session</h2>
            {artifactUrl && (
              <a
                href={artifactUrl}
                target="_blank"
                rel="noreferrer noopener"
                className="text-sm inline-flex items-center gap-1 text-rose-700 hover:underline"
              >
                Risk Artifact <ExternalLink className="w-3 h-3" />
              </a>
            )}
          </div>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            <dt className="text-slate-500">Session id</dt>
            <dd className="font-mono">{session.session_id}</dd>
            <dt className="text-slate-500">Technique</dt>
            <dd>{probeResult.technique}</dd>
            <dt className="text-slate-500">Decision</dt>
            <dd>{probeResult.decision_reason || "(authorized)"}</dd>
            <dt className="text-slate-500">Disclosure</dt>
            <dd>{probeResult.effective_disclosure}</dd>
            <dt className="text-slate-500">Duration</dt>
            <dd>{probeResult.duration_seconds.toFixed(2)} s</dd>
            <dt className="text-slate-500">Attempts</dt>
            <dd>{probeResult.n_attempts}</dd>
            <dt className="text-slate-500">Aborted</dt>
            <dd>{probeResult.aborted_reason ?? "no"}</dd>
          </dl>
          {verify && (
            <div className="pt-3 border-t border-slate-100 dark:border-slate-800">
              <p className="text-sm flex items-center gap-2">
                <span className="text-slate-500">Chain:</span>
                {verify.status === "ok" ? (
                  <Badge className="bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200">
                    <CheckCircle2 className="w-3 h-3 inline mr-1" />
                    OK ({verify.rows_verified} rows verified)
                  </Badge>
                ) : (
                  <Badge className="bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200">
                    {verify.status.toUpperCase()} {verify.reason}
                  </Badge>
                )}
              </p>
            </div>
          )}
        </section>
      )}

      {/* ── Trace timeline ─────────────────────────────────────────────────── */}
      {traces.length > 0 && (
        <section className="bg-white dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700 p-5 space-y-3">
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <FileText className="w-5 h-5" /> Trace timeline ({traces.length})
          </h2>
          <ol className="space-y-2">
            {traces.map((t) => (
              <li
                key={t.id}
                className="border-l-4 border-rose-700 bg-slate-50 dark:bg-slate-800/40 px-3 py-2"
              >
                <div className="text-xs text-slate-500 flex items-center gap-2">
                  <span>{new Date(t.created_at).toLocaleTimeString()}</span>
                  <span className="font-semibold uppercase">{t.kind}</span>
                  {t.verdict && (
                    <Badge
                      className={
                        t.verdict === "leaked"
                          ? "bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-200"
                          : "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                      }
                    >
                      {t.verdict}
                    </Badge>
                  )}
                  {t.engine && <span className="opacity-70">{t.engine}</span>}
                  <span className="font-mono opacity-50">{t.row_signature.slice(0, 12)}</span>
                </div>
                <pre className="text-xs font-mono mt-1 overflow-x-auto whitespace-pre-wrap break-words">
                  {prettyPayload(t.payload_json)}
                </pre>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function prettyPayload(blob: string): string {
  if (!blob) return "(empty)";
  try {
    const obj = JSON.parse(blob);
    return JSON.stringify(obj, null, 2);
  } catch {
    return blob;
  }
}

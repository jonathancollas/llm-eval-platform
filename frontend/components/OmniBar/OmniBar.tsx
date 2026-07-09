"use client";
/**
 * OmniBar — the single surface of intention for Mercury Retrograde.
 *
 * Three modes share state and backend calls:
 *   - "hero"    — fullscreen home search
 *   - "compact" — collapsed topbar slot (opens overlay on click)
 *   - "overlay" — modal Cmd+K triggered from anywhere
 *
 * The component consumes the discriminated IntentPayload from the backend
 * (backend/eval_engine/search/schema.py) and narrows to the right renderer
 * per intent kind. No prop drilling, no context required; parent passes mode.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { buildHeaders, classifyIntent, fetchTypeahead, executeIntent, resolveApiEndpoint } from "./api";
import type {
  IntentResponse,
  IntentPayload,
  TypeaheadResponse,
  OmniBarMode,
} from "./types";

const DEBOUNCE_MS = 120;

export interface OmniBarProps {
  mode: OmniBarMode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  placeholder?: string;
  /** User role — determines ATTACK availability. */
  role?: "viewer" | "evaluator" | "admin";
}

export function OmniBar({
  mode,
  open = false,
  onOpenChange,
  placeholder = "Ask about a model, launch an evaluation, or red-team a system…",
  role = "viewer",
}: OmniBarProps) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounce
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  // Intent (only when query is meaningful)
  const { data: intent, isLoading: intentLoading } = useSWR<IntentResponse | null>(
    debounced.length >= 2 ? (["intent", debounced] as const) : null,
    async ([, q]: readonly [string, string]) => classifyIntent(q).catch(() => null),
    { dedupingInterval: 1500, revalidateOnFocus: false, keepPreviousData: true }
  );

  // Typeahead (always, when the bar is open-ish)
  const typeaheadEnabled = mode !== "compact" && debounced.length >= 1;
  const { data: typeahead } = useSWR<TypeaheadResponse | null>(
    typeaheadEnabled ? (["typeahead", debounced] as const) : null,
    async ([, q]: readonly [string, string]) => fetchTypeahead(q, 5),
    { dedupingInterval: 800, revalidateOnFocus: false, keepPreviousData: true }
  );

  // Focus management
  useEffect(() => {
    if (mode === "hero" || (mode === "overlay" && open)) {
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [mode, open]);

  // Execute (Enter key)
  const onExecute = useCallback(async () => {
    if (!intent || isExecuting) return;
    setIsExecuting(true);
    try {
      const payload = intent.payload;
      if (payload.kind === "navigate") {
        router.push(payload.route);
        if (mode === "overlay") onOpenChange?.(false);
      } else if (payload.kind === "launch" && payload.preview) {
        // Call /execute to get the ready-to-submit body
        const { submit_body, submit_endpoint } = await executeIntent({
          query: intent.query, role,
        });
        if (submit_body && submit_endpoint) {
          const res = await fetch(resolveApiEndpoint(submit_endpoint), {
            method: "POST",
            headers: buildHeaders({ "Content-Type": "application/json" }),
            body: JSON.stringify(submit_body),
          });
          if (res.ok) {
            await res.json();
            router.push("/campaigns");
            if (mode === "overlay") onOpenChange?.(false);
          } else {
            throw new Error(`launch failed: ${res.status}`);
          }
        }
      } else if (payload.kind === "attack") {
        // Redirect to Red Room with prefilled state — user confirms there
        const params = new URLSearchParams();
        if (payload.target_model_id != null) {
          params.set("target", String(payload.target_model_id));
        }
        if (payload.goal) params.set("goal", payload.goal);
        params.set("aggressiveness", String(payload.aggressiveness));
        router.push(`/redbox?${params.toString()}`);
        if (mode === "overlay") onOpenChange?.(false);
      }
      // ASK: nothing to execute — answer is already shown
    } catch (e) {
      console.error("[omnibar] execute failed:", e);
    } finally {
      setIsExecuting(false);
    }
  }, [intent, isExecuting, role, router, mode, onOpenChange]);

  // ─── Rendering ───────────────────────────────────────────────────────────

  if (mode === "compact") return <Compact onClick={() => onOpenChange?.(true)} placeholder={placeholder} />;

  const showResults = !!intent && query.trim().length >= 2;

  const inputCommon = (
    <input
      ref={inputRef}
      type="text"
      value={query}
      onChange={(e) => setQuery(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); onExecute(); }
        if (e.key === "Escape" && mode === "overlay") { onOpenChange?.(false); }
      }}
      placeholder={placeholder}
      spellCheck={false}
      autoComplete="off"
      className="omni-input"
    />
  );

  if (mode === "hero") {
    return (
      <div className="omni-hero">
        <div className="omni-hero__brand">
          <div className="omni-hero__sigil" aria-hidden>☿</div>
          <h1>An observatory for <em>frontier AI behavior</em>.</h1>
          <div className="omni-hero__tag">— Measure what moves —</div>
        </div>
        <div className="omni-hero__field">
          <div className="omni-hero__label">
            <span>§ Query · natural language</span>
            {intent && <IntentBadge intent={intent} />}
          </div>
          <div className="omni-hero__wrap">{inputCommon}</div>
          <div className="omni-hero__foot">
            <span><kbd>⏎</kbd> execute · <kbd>⌘K</kbd> opens anywhere</span>
            <span>
              {intentLoading
                ? <><span className="omni-pulse" /> classifying…</>
                : intent
                ? <><span className="omni-pulse" /> {intent.intent} · {(intent.confidence * 100).toFixed(0)}% · {intent.latency_ms}ms</>
                : <><span className="omni-pulse" /> ready</>}
            </span>
          </div>
        </div>
        {showResults && intent && <IntentRenderer intent={intent} onExecute={onExecute} />}
        {!showResults && typeahead && typeahead.groups.length > 0 && (
          <TypeaheadRenderer data={typeahead} onPick={(href) => router.push(href)} />
        )}
        {!showResults && !typeahead?.groups.length && (
          <div className="omni-hero__quote">
            “Mercury retrograde is an optical illusion. We measure what actually moves.”
          </div>
        )}
        <OmniStyles />
      </div>
    );
  }

  // mode === "overlay"
  if (!open) return null;
  return (
    <div className="omni-veil" role="dialog" aria-modal="true"
         onClick={(e) => e.target === e.currentTarget && onOpenChange?.(false)}>
      <div className="omni-panel">
        <div className="omni-overlay__row">
          <span className="omni-overlay__glyph">§</span>
          <div className="omni-overlay__wrap">{inputCommon}</div>
          <span className="omni-overlay__esc"><kbd>esc</kbd> close</span>
        </div>
        {intent && <IntentBadgeStrip intent={intent} />}
        <div className="omni-overlay__body">
          {showResults && intent && <IntentRenderer intent={intent} onExecute={onExecute} compact />}
          {!showResults && typeahead && typeahead.groups.length > 0 && (
            <TypeaheadRenderer data={typeahead} onPick={(href) => {
              router.push(href); onOpenChange?.(false);
            }} compact />
          )}
          {!showResults && !typeahead?.groups.length && (
            <div className="omni-overlay__empty">
              Type to begin. Natural language is supported.<br />
              <span className="hint">
                <kbd>!</kbd>attack · <kbd>?</kbd>ask · <kbd>@</kbd>model · <kbd>#</kbd>benchmark
              </span>
            </div>
          )}
        </div>
        <div className="omni-overlay__foot">
          <span><kbd>⏎</kbd> execute · <kbd>Tab</kbd> disambiguate</span>
          <span>
            {intent
              ? `${intent.intent} · ${(intent.confidence * 100).toFixed(0)}% · ${intent.latency_ms}ms`
              : "ready"}
          </span>
        </div>
      </div>
      <OmniStyles />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Compact mode — non-editable chip that opens the overlay
// ═══════════════════════════════════════════════════════════════════════════

function Compact({ onClick, placeholder }: { onClick: () => void; placeholder: string }) {
  return (
    <button type="button" className="omni-compact" onClick={onClick} aria-label="Open search (Cmd+K)">
      <span className="omni-compact__glyph">§</span>
      <span className="omni-compact__ph">{placeholder}</span>
      <span className="omni-compact__kbd"><kbd>⌘</kbd><kbd>K</kbd></span>
      <OmniStyles />
    </button>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Intent rendering — discriminated on payload.kind
// ═══════════════════════════════════════════════════════════════════════════

function IntentRenderer({
  intent, onExecute, compact = false,
}: { intent: IntentResponse; onExecute: () => void; compact?: boolean }) {
  const { payload } = intent;
  switch (payload.kind) {
    case "navigate":
      return <NavigateView payload={payload} compact={compact} />;
    case "ask":
      return <AskView payload={payload} compact={compact} />;
    case "launch":
      return <LaunchView payload={payload} onExecute={onExecute} compact={compact} />;
    case "attack":
      return <AttackView payload={payload} onExecute={onExecute} compact={compact} />;
  }
}

function NavigateView({ payload, compact }: { payload: Extract<IntentPayload, { kind: "navigate" }>; compact?: boolean }) {
  return (
    <div className={compact ? "omni-result omni-result--compact" : "omni-result"}>
      <div className="omni-result__head">→ Navigate</div>
      <div className="omni-result__body">
        <div className="omni-nav-target">
          <div className="omni-nav-target__label">{payload.label || payload.route}</div>
          <div className="omni-nav-target__route">{payload.route}</div>
        </div>
      </div>
    </div>
  );
}

function AskView({ payload, compact }: { payload: Extract<IntentPayload, { kind: "ask" }>; compact?: boolean }) {
  return (
    <div className={compact ? "omni-result omni-result--compact" : "omni-result"}>
      <div className="omni-result__head">
        ? Answer {payload.deterministic && <span className="omni-tag">deterministic</span>}
      </div>
      <div className="omni-result__body">
        <div className="omni-ask-answer">{payload.answer}</div>
        {payload.sources.length > 0 && (
          <div className="omni-ask-sources">
            {payload.sources.map((s, i) => (
              <a key={s.id} href={s.href ?? "#"} className="omni-src">
                <span className="omni-src__n">[{i + 1}]</span>
                <span className="omni-src__l">{s.label}</span>
                {s.snippet && <span className="omni-src__s">{s.snippet}</span>}
              </a>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function LaunchView({
  payload, onExecute, compact,
}: { payload: Extract<IntentPayload, { kind: "launch" }>; onExecute: () => void; compact?: boolean }) {
  if (payload.clarification) {
    return (
      <div className={compact ? "omni-result omni-result--compact" : "omni-result"}>
        <div className="omni-result__head">▶ Launch — clarification</div>
        <div className="omni-result__body"><em>{payload.clarification}</em></div>
      </div>
    );
  }
  const p = payload.preview;
  if (!p) return null;
  return (
    <div className={compact ? "omni-result omni-result--compact omni-result--launch" : "omni-result omni-result--launch"}>
      <div className="omni-result__head">▶ Campaign preview · confirm to submit</div>
      <div className="omni-result__body">
        <div className="omni-launch-grid">
          <Field label="Name"        value={p.name} wide />
          <Field label="Samples"     value={String(p.max_samples)} mono />
          <Field label="Temperature" value={p.temperature.toFixed(1)} mono />
          <Field label="Est. cost"   value={`$${p.estimated_cost_usd.toFixed(2)}`} mono accent />
          <Field label="Est. time"   value={`~${p.estimated_time_minutes.toFixed(0)}min`} mono />
          <Field label="Models × Benchmarks"
                 value={`${p.model_ids.length} × ${p.benchmark_ids.length}`} mono />
        </div>
        {p.needs_confirmation.length > 0 && (
          <div className="omni-needs">
            <strong>Needs confirmation:</strong>{" "}
            {p.needs_confirmation.join(" · ")}
          </div>
        )}
      </div>
      <div className="omni-result__foot">
        <span className="foot-hint">Edit any field — or submit as-is</span>
        <button className="omni-btn" onClick={onExecute}>Launch campaign →</button>
      </div>
    </div>
  );
}

function AttackView({
  payload, onExecute, compact,
}: { payload: Extract<IntentPayload, { kind: "attack" }>; onExecute: () => void; compact?: boolean }) {
  if (payload.clarification) {
    return (
      <div className={compact ? "omni-result omni-result--compact" : "omni-result omni-result--attack"}>
        <div className="omni-result__head" style={{ color: "var(--omni-vermillion, #C9302C)" }}>
          ! Red Room — clarification
        </div>
        <div className="omni-result__body"><em>{payload.clarification}</em></div>
      </div>
    );
  }
  return (
    <div className={compact ? "omni-result omni-result--compact omni-result--attack" : "omni-result omni-result--attack"}>
      <div className="omni-result__head" style={{ color: "var(--omni-vermillion, #C9302C)" }}>
        ! Red Room · adversarial session · restricted
      </div>
      <div className="omni-result__body">
        <div className="omni-launch-grid">
          <Field label="Target model" value={payload.target_model_name ?? "—"} wide />
          <Field label="Aggressiveness" value={`L${payload.aggressiveness}`} mono accent />
          <Field label="Autonomy"      value={payload.autonomy_level} mono />
          <Field label="Goal"          value={payload.goal || "(none specified)"} wide />
          <Field label="Engines"       value={payload.engines.join(" · ") || "native"} mono />
          <Field label="Required role" value={payload.requires_role} mono accent />
        </div>
      </div>
      <div className="omni-result__foot">
        <span className="foot-hint">Confirmation required · results signed and archived</span>
        <button className="omni-btn omni-btn--danger" onClick={onExecute}>Open Red Room →</button>
      </div>
    </div>
  );
}

function Field({
  label, value, wide = false, mono = false, accent = false,
}: { label: string; value: string; wide?: boolean; mono?: boolean; accent?: boolean }) {
  const cls = [
    "omni-field",
    wide ? "omni-field--wide" : "",
    mono ? "omni-field--mono" : "",
    accent ? "omni-field--accent" : "",
  ].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      <div className="omni-field__lbl">{label}</div>
      <div className="omni-field__val">{value}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Typeahead renderer
// ═══════════════════════════════════════════════════════════════════════════

function TypeaheadRenderer({
  data, onPick, compact = false,
}: { data: TypeaheadResponse; onPick: (href: string) => void; compact?: boolean }) {
  if (data.groups.length === 0) return null;
  return (
    <div className={compact ? "omni-ta omni-ta--compact" : "omni-ta"}>
      {data.groups.map((g) => (
        <div className="omni-ta__group" key={g.kind}>
          <div className="omni-ta__head">
            <span>{g.label}</span><span className="omni-ta__count">{g.items.length}</span>
          </div>
          {g.items.map((item) => (
            <button
              key={item.id}
              type="button"
              className="omni-ta__item"
              onClick={() => item.href && onPick(item.href)}
              disabled={!item.href}
            >
              <span className="omni-ta__sym">{item.kind}</span>
              <span className="omni-ta__label">{item.label}</span>
              {item.subtitle && <span className="omni-ta__sub">{item.subtitle}</span>}
              {item.action_hint && <span className="omni-ta__hint">{item.action_hint}</span>}
            </button>
          ))}
        </div>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Intent badge
// ═══════════════════════════════════════════════════════════════════════════

function IntentBadge({ intent }: { intent: IntentResponse }) {
  const dots = Math.max(1, Math.min(4, Math.round(intent.confidence * 4)));
  return (
    <span className={`omni-intent omni-intent--${intent.intent}`}>
      {intent.intent.toUpperCase()}
      <span className="omni-intent__dots">
        {[1, 2, 3, 4].map(i => <span key={i} className={i <= dots ? "on" : "off"} />)}
      </span>
    </span>
  );
}

function IntentBadgeStrip({ intent }: { intent: IntentResponse }) {
  return (
    <div className="omni-overlay__ctx">
      <IntentBadge intent={intent} />
      {intent.can_auto_execute && <span className="omni-auto">auto-execute enabled</span>}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════
//  Styles — all CSS variables so the app theme controls appearance
// ═══════════════════════════════════════════════════════════════════════════

function OmniStyles() {
  return (
    <style>{`
      :root {
        --omni-ink: #0E0A1A;
        --omni-ink-2: #1A1430;
        --omni-bone: #F1ECE0;
        --omni-bone-2: #E8E0D0;
        --omni-bone-3: #D6CBB3;
        --omni-mute: #8A7F6C;
        --omni-faint: #5A5242;
        --omni-vermillion: #C9302C;
        --omni-verdigris: #3E7A6B;
        --omni-rule: rgba(14,10,26,0.10);
        --omni-rule-2: rgba(14,10,26,0.06);
      }
      .omni-hero {
        max-width: 780px;
        margin: 0 auto;
        padding: 72px 40px 40px;
        min-height: 100vh;
      }
      .omni-hero__brand { text-align: center; margin-bottom: 48px; }
      .omni-hero__sigil {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 400;
        font-size: 88px; line-height: 1;
        color: var(--omni-ink); margin-bottom: 4px;
      }
      .omni-hero__brand h1 {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 320;
        font-style: italic;
        font-size: 32px;
        margin: 0 0 6px;
        color: var(--omni-ink);
        letter-spacing: -0.01em;
      }
      .omni-hero__brand h1 em {
        font-style: normal;
        font-variation-settings: "opsz" 144, "wght" 500;
      }
      .omni-hero__tag {
        font-family: 'Geist', system-ui, sans-serif;
        font-size: 11px;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        color: var(--omni-mute);
      }
      .omni-hero__label {
        display: flex; justify-content: space-between; align-items: center;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px;
        letter-spacing: 0.18em; text-transform: uppercase;
        color: var(--omni-mute); margin-bottom: 10px;
      }
      .omni-hero__wrap {
        padding: 24px 28px;
        background: var(--omni-bone);
        border: 1px solid var(--omni-rule);
        border-top: 2px solid var(--omni-ink);
      }
      .omni-hero__wrap:focus-within { border-color: var(--omni-ink); }
      .omni-hero__wrap .omni-input {
        width: 100%;
        border: none;
        outline: none;
        background: transparent;
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 350;
        font-size: 30px; line-height: 1.2;
        color: var(--omni-ink);
        letter-spacing: -0.015em;
      }
      .omni-hero__wrap .omni-input::placeholder {
        color: var(--omni-mute);
        font-style: italic;
        font-variation-settings: "opsz" 144, "wght" 300;
      }
      .omni-hero__foot {
        display: flex; justify-content: space-between; align-items: center;
        padding: 10px 28px;
        border: 1px solid var(--omni-rule);
        border-top: none;
        background: rgba(14,10,26,0.015);
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 11px; color: var(--omni-faint);
      }
      .omni-hero__foot kbd {
        font: inherit; font-size: 10px;
        background: var(--omni-bone-2);
        border: 1px solid var(--omni-rule);
        padding: 1px 5px;
        margin: 0 2px; border-radius: 2px; color: var(--omni-ink);
      }
      .omni-pulse {
        display: inline-block; width: 5px; height: 5px; border-radius: 50%;
        background: var(--omni-verdigris);
        box-shadow: 0 0 6px var(--omni-verdigris);
        margin-right: 6px;
        animation: omni-pulse 1.8s ease-in-out infinite;
      }
      @keyframes omni-pulse { 0%,100%{opacity:.4} 50%{opacity:1} }
      .omni-hero__quote {
        margin: 80px auto 30px;
        padding-top: 40px;
        border-top: 1px solid var(--omni-rule);
        text-align: center;
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-style: italic;
        font-variation-settings: "opsz" 144, "wght" 320;
        font-size: 15px;
        color: var(--omni-faint);
      }

      /* Compact */
      .omni-compact {
        width: 100%; max-width: 640px;
        display: flex; align-items: center; gap: 10px;
        padding: 7px 14px;
        background: var(--omni-bone);
        border: 1px solid var(--omni-rule); border-radius: 2px;
        cursor: text; font: inherit; color: inherit; text-align: left;
        transition: border-color 140ms ease;
      }
      .omni-compact:hover { border-color: rgba(14,10,26,0.25); }
      .omni-compact__glyph {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        color: var(--omni-mute); font-size: 13px;
      }
      .omni-compact__ph {
        flex: 1;
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 330;
        font-style: italic; color: var(--omni-mute);
        font-size: 14px;
        white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
      }
      .omni-compact__kbd { display: flex; gap: 3px; }
      .omni-compact__kbd kbd {
        background: var(--omni-bone-2); border: 1px solid var(--omni-rule);
        padding: 1px 5px; font-family: 'JetBrains Mono', monospace;
        font-size: 9px; color: var(--omni-ink); border-radius: 2px;
      }

      /* Overlay */
      .omni-veil {
        position: fixed; inset: 0; z-index: 9999;
        background: rgba(14,10,26,0.55);
        backdrop-filter: blur(6px);
        display: flex; align-items: flex-start; justify-content: center;
        padding: 120px 24px 40px;
        animation: omni-veil 180ms ease;
      }
      @keyframes omni-veil { from{opacity:0} to{opacity:1} }
      .omni-panel {
        width: 100%; max-width: 640px;
        background: var(--omni-bone);
        border: 1px solid var(--omni-ink);
        box-shadow: 0 24px 80px rgba(14,10,26,0.35);
        animation: omni-rise 240ms cubic-bezier(0.22,1,0.36,1);
        max-height: calc(100vh - 160px);
        display: flex; flex-direction: column;
      }
      @keyframes omni-rise {
        from { opacity: 0; transform: translateY(16px) scale(.98); }
        to { opacity: 1; transform: translateY(0) scale(1); }
      }
      .omni-overlay__row {
        display: flex; align-items: center; padding: 18px 22px; gap: 14px;
        border-bottom: 1px solid var(--omni-rule);
      }
      .omni-overlay__glyph {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 500;
        font-size: 22px; color: var(--omni-ink);
      }
      .omni-overlay__wrap { flex: 1; }
      .omni-overlay__wrap .omni-input {
        width: 100%; border: none; outline: none; background: transparent;
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 380;
        font-size: 22px; color: var(--omni-ink); letter-spacing: -0.01em;
      }
      .omni-overlay__wrap .omni-input::placeholder {
        color: var(--omni-mute); font-style: italic;
      }
      .omni-overlay__esc {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; color: var(--omni-mute);
      }
      .omni-overlay__esc kbd {
        background: var(--omni-bone-2); border: 1px solid var(--omni-rule);
        padding: 2px 6px; border-radius: 2px; font: inherit;
        font-size: 9px; color: var(--omni-ink);
      }
      .omni-overlay__ctx {
        padding: 8px 22px; background: rgba(14,10,26,0.025);
        border-bottom: 1px solid var(--omni-rule-2);
        display: flex; gap: 10px; align-items: center;
      }
      .omni-overlay__body { flex: 1; overflow-y: auto; min-height: 0; }
      .omni-overlay__empty {
        padding: 40px 22px; text-align: center; color: var(--omni-faint);
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "wght" 360; font-size: 15px; font-style: italic;
      }
      .omni-overlay__empty .hint {
        display: block; margin-top: 12px; font-style: normal; font-size: 11px;
        font-family: 'JetBrains Mono', monospace; color: var(--omni-mute);
      }
      .omni-overlay__empty kbd {
        font: inherit; background: var(--omni-bone-2);
        border: 1px solid var(--omni-rule); padding: 1px 5px; margin: 0 2px;
      }
      .omni-overlay__foot {
        padding: 10px 22px; border-top: 1px solid var(--omni-rule);
        display: flex; justify-content: space-between; align-items: center;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; color: var(--omni-mute);
        background: rgba(14,10,26,0.015);
      }
      .omni-overlay__foot kbd {
        background: var(--omni-bone-2); border: 1px solid var(--omni-rule);
        padding: 1px 5px; font: inherit; font-size: 9px; color: var(--omni-ink);
      }

      /* Intent badge */
      .omni-intent {
        display: inline-flex; align-items: center; gap: 6px;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
        padding: 3px 8px; border: 1px solid currentColor;
      }
      .omni-intent--navigate { color: var(--omni-faint); }
      .omni-intent--ask      { color: #2E4A6E; }
      .omni-intent--launch   { color: var(--omni-verdigris); }
      .omni-intent--attack   { color: var(--omni-vermillion); background: rgba(201,48,44,0.08); }
      .omni-intent--unknown  { color: var(--omni-mute); }
      .omni-intent__dots { display: inline-flex; gap: 2px; }
      .omni-intent__dots span {
        width: 3px; height: 3px; border-radius: 50%;
        background: var(--omni-bone-3);
      }
      .omni-intent__dots span.on { background: currentColor; }
      .omni-auto {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: var(--omni-verdigris);
        letter-spacing: 0.08em;
      }

      /* Result panel */
      .omni-result {
        margin: 24px auto 0; max-width: 780px;
        background: var(--omni-bone);
        border: 1px solid var(--omni-rule);
      }
      .omni-result--compact { margin: 0; border: none; border-bottom: 1px solid var(--omni-rule-2); }
      .omni-result--attack { border-color: var(--omni-vermillion); }
      .omni-result__head {
        padding: 12px 20px;
        border-bottom: 1px solid var(--omni-rule-2);
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
        color: var(--omni-ink);
      }
      .omni-result__body { padding: 20px; }
      .omni-result__foot {
        padding: 12px 20px; border-top: 1px solid var(--omni-rule-2);
        display: flex; justify-content: space-between; align-items: center;
        background: rgba(14,10,26,0.02);
      }
      .omni-btn {
        font-family: 'Geist', sans-serif; font-weight: 500; font-size: 13px;
        padding: 8px 16px;
        border: 1px solid var(--omni-ink); background: var(--omni-ink);
        color: var(--omni-bone); cursor: pointer;
        transition: all 160ms ease;
      }
      .omni-btn:hover { background: transparent; color: var(--omni-ink); }
      .omni-btn--danger { background: var(--omni-vermillion); border-color: var(--omni-vermillion); }
      .omni-btn--danger:hover { background: transparent; color: var(--omni-vermillion); }
      .foot-hint {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; color: var(--omni-mute);
      }

      .omni-nav-target__label {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 450;
        font-size: 18px; color: var(--omni-ink);
      }
      .omni-nav-target__route {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 12px; color: var(--omni-faint); margin-top: 4px;
      }

      .omni-tag {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 9px; color: var(--omni-verdigris);
        padding: 1px 5px; border: 1px solid currentColor;
        letter-spacing: 0.1em; margin-left: 8px;
      }
      .omni-ask-answer {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 350;
        font-size: 17px; line-height: 1.5; color: var(--omni-ink);
      }
      .omni-ask-sources {
        margin-top: 16px; display: grid; gap: 8px;
        grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
      }
      .omni-src {
        padding: 10px 12px; border: 1px solid var(--omni-rule);
        background: rgba(14,10,26,0.015);
        font-size: 12px; text-decoration: none; color: inherit;
        display: block;
      }
      .omni-src:hover { border-color: var(--omni-vermillion); }
      .omni-src__n {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        color: var(--omni-vermillion); font-size: 10px; display: block;
      }
      .omni-src__l {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "wght" 450;
        color: var(--omni-ink);
      }
      .omni-src__s {
        display: block; margin-top: 4px;
        font-family: 'Geist', sans-serif;
        font-size: 11px; color: var(--omni-faint);
      }

      .omni-launch-grid {
        display: grid; grid-template-columns: repeat(3, 1fr);
        gap: 16px 24px;
      }
      .omni-field {}
      .omni-field--wide { grid-column: span 3; }
      .omni-field__lbl {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase;
        color: var(--omni-mute); margin-bottom: 4px;
      }
      .omni-field__val {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "opsz" 144, "wght" 440;
        font-size: 18px; color: var(--omni-ink); letter-spacing: -0.01em;
      }
      .omni-field--mono .omni-field__val {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 14px; letter-spacing: 0;
      }
      .omni-field--accent .omni-field__val { color: var(--omni-vermillion); }
      .omni-result--launch .omni-field--accent .omni-field__val { color: var(--omni-verdigris); }
      .omni-needs {
        margin-top: 16px; padding: 10px 12px;
        background: rgba(201,48,44,0.05);
        border-left: 2px solid var(--omni-vermillion);
        font-size: 12px; color: var(--omni-ink);
      }

      /* Typeahead */
      .omni-ta { margin: 24px auto 0; max-width: 780px; }
      .omni-ta--compact { margin: 0; }
      .omni-ta__group { margin-bottom: 8px; }
      .omni-ta__head {
        padding: 10px 20px 6px;
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 9px; letter-spacing: 0.22em; text-transform: uppercase;
        color: var(--omni-mute);
        background: rgba(14,10,26,0.02);
        border-bottom: 1px solid var(--omni-rule-2);
        display: flex; justify-content: space-between;
      }
      .omni-ta__count { color: var(--omni-bone-3); }
      .omni-ta__item {
        width: 100%;
        padding: 10px 20px;
        display: grid;
        grid-template-columns: 80px 1fr auto;
        gap: 10px;
        align-items: center;
        cursor: pointer; background: transparent;
        border: none; border-bottom: 1px solid var(--omni-rule-2);
        text-align: left; font: inherit;
        transition: background 120ms ease, padding-left 140ms ease;
      }
      .omni-ta__item:hover:not(:disabled) {
        background: var(--omni-bone-2); padding-left: 26px;
      }
      .omni-ta__item:disabled { cursor: default; opacity: 0.5; }
      .omni-ta__sym {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; color: var(--omni-mute); letter-spacing: 0.06em;
      }
      .omni-ta__label {
        font-family: 'Fraunces', ui-serif, Georgia, serif;
        font-variation-settings: "wght" 430;
        font-size: 15px; color: var(--omni-ink);
      }
      .omni-ta__sub {
        font-family: 'JetBrains Mono', ui-monospace, monospace;
        font-size: 10px; color: var(--omni-faint);
      }
      .omni-ta__hint {
        font-family: 'Geist', sans-serif;
        font-size: 11px; color: var(--omni-verdigris);
      }
    `}</style>
  );
}

// Expose OmniStyles for consumers that may want to include it once
export { OmniStyles };

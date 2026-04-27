"use client";
/**
 * RelatedViews — the lateral panel that replaces the flat Sidebar.
 *
 * Given an entity type and id, it renders the semantically related views
 * based on the navigation graph. Counts (e.g., "Run history · 12 →") are
 * fetched from /api/navigation/counts and shown when available.
 *
 * Usage inside a page:
 *
 *   <RelatedViews entityType="model" entityId={model.id} />
 *
 * Or with role gating (for admin-only views):
 *
 *   <RelatedViews entityType="tenant" entityId={t.id} role="admin" />
 *
 * The component returns null when no links are visible (for example, an
 * unknown entity type or all links gated above the user's role) — pages can
 * render it unconditionally without worrying about empty states.
 */
import Link from "next/link";
import useSWR from "swr";
import { API_BASE, API_KEY } from "@/lib/config";
import {
  getRelatedViews,
  type EntityType,
  type Role,
} from "@/lib/navigation-graph";

interface RelatedViewsProps {
  entityType: EntityType;
  entityId: string | number;
  /** When true (default), counts are fetched from the backend and displayed. */
  fetchCounts?: boolean;
  /** User role for filtering role-gated links. Default: "viewer". */
  role?: Role;
  /** Optional heading override. Default: "Related views". */
  heading?: string;
}

async function fetchCounts(
  entityType: string,
  entityId: string | number
): Promise<Record<string, number>> {
  const url = `${API_BASE}/navigation/counts?entity_type=${encodeURIComponent(
    entityType
  )}&entity_id=${encodeURIComponent(String(entityId))}`;
  const headers = new Headers();
  if (API_KEY) headers.set("X-API-Key", API_KEY);
  const res = await fetch(url, { headers });
  if (!res.ok) return {};
  return res.json();
}

export function RelatedViews({
  entityType,
  entityId,
  fetchCounts: doFetchCounts = true,
  role = "viewer",
  heading = "Related views",
}: RelatedViewsProps) {
  const visible = getRelatedViews(entityType, entityId, role);

  const { data: counts } = useSWR(
    doFetchCounts ? (["nav-counts", entityType, entityId] as const) : null,
    ([, t, i]: readonly [string, string, string | number]) => fetchCounts(t, i),
    { dedupingInterval: 30_000, revalidateOnFocus: false }
  );

  if (visible.length === 0) return null;

  return (
    <aside className="rv" aria-label={heading}>
      <div className="rv-head">{heading}</div>
      <ul>
        {visible.map((v) => {
          const count = counts?.[v.key];
          return (
            <li key={v.key}>
              <Link href={v.href} className={v.elevated ? "rv-link rv-link--elev" : "rv-link"}>
                <span className="label">{v.label}</span>
                <span className="arrow">
                  {typeof count === "number" && (
                    <span className="count">{count}</span>
                  )}
                  <span aria-hidden> →</span>
                </span>
              </Link>
            </li>
          );
        })}
      </ul>

      <style jsx>{`
        .rv {
          min-width: 280px;
          max-width: 360px;
          border-left: 1px solid var(--omni-rule, rgba(14, 10, 26, 0.1));
          padding-left: 22px;
        }
        .rv-head {
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 9px;
          letter-spacing: 0.22em;
          text-transform: uppercase;
          color: var(--omni-mute, #8a7f6c);
          margin-bottom: 10px;
        }
        ul {
          list-style: none;
          margin: 0;
          padding: 0;
          display: flex;
          flex-direction: column;
          gap: 0;
        }
        li :global(.rv-link) {
          display: flex;
          justify-content: space-between;
          align-items: center;
          padding: 8px 0;
          color: var(--omni-ink, #0e0a1a);
          text-decoration: none;
          font-family: "Fraunces", ui-serif, Georgia, serif;
          font-size: 14px;
          font-variation-settings: "wght" 420;
          letter-spacing: -0.005em;
          border-bottom: 1px solid var(--omni-rule-2, rgba(14, 10, 26, 0.06));
          transition: padding-left 160ms ease, color 160ms ease;
        }
        li:last-child :global(.rv-link) {
          border-bottom: none;
        }
        li :global(.rv-link:hover) {
          padding-left: 6px;
          color: var(--omni-vermillion, #c9302c);
        }
        li :global(.rv-link--elev) {
          color: var(--omni-vermillion, #c9302c);
          font-variation-settings: "wght" 460;
        }
        li :global(.arrow) {
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 11px;
          color: var(--omni-bone-3, #d6cbb3);
          display: inline-flex;
          gap: 6px;
          align-items: center;
        }
        li :global(.count) {
          color: var(--omni-faint, #5a5242);
          font-size: 10px;
          letter-spacing: 0.08em;
        }
        li :global(.rv-link:hover .arrow),
        li :global(.rv-link:hover .count) {
          color: var(--omni-vermillion, #c9302c);
        }

        @media (max-width: 840px) {
          .rv {
            min-width: 0;
            max-width: none;
            border-left: none;
            border-top: 1px solid var(--omni-rule, rgba(14, 10, 26, 0.1));
            padding-left: 0;
            padding-top: 16px;
            width: 100%;
          }
        }
      `}</style>
    </aside>
  );
}

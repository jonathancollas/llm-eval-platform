"use client";
/**
 * Topbar — the new chrome. Replaces <Sidebar>.
 *
 * Three zones in a 3-column grid:
 *   ├─ left:   brand mark (☿ + name + version)
 *   ├─ center: compact OmniBar — clicking it opens the global overlay
 *   └─ right:  tenant/user status (queue indicator + user chip)
 *
 * The Topbar is sticky at the top. It uses backdrop-filter blur so content
 * scrolling beneath it remains visible but soft.
 *
 * Note: the Topbar itself does NOT manage Cmd+K — that's the
 * OmniBarProvider's job. The Topbar only renders the COMPACT OmniBar mode,
 * which is a button that triggers `setOpen(true)` from the provider.
 */
import Link from "next/link";
import { OmniBar } from "@/components/OmniBar/OmniBar";
import { useOmniBar } from "@/components/OmniBar/OmniBarProvider";

const APP_VERSION = process.env.NEXT_PUBLIC_APP_VERSION ?? "v0.1";

export function Topbar() {
  const { setOpen } = useOmniBar();

  return (
    <header className="mr-topbar">
      <div className="mr-brand">
        <Link href="/" aria-label="Home" className="mr-mark">☿</Link>
        <Link href="/" className="mr-name">Mercury Retrograde</Link>
        <span className="mr-v" aria-hidden>{APP_VERSION}</span>
      </div>

      <div className="mr-search-slot">
        <OmniBar
          mode="compact"
          onOpenChange={setOpen}
          placeholder="Search models, benchmarks, campaigns…  ⌘K"
        />
      </div>

      <div className="mr-user">
        <span className="mr-dot" aria-hidden />
        <span className="mr-status">queue idle</span>
        <div className="mr-avatar" aria-hidden />
        <span className="mr-tenant">default</span>
      </div>

      <style jsx>{`
        .mr-topbar {
          position: sticky;
          top: 0;
          z-index: 100;
          background: rgba(241, 236, 224, 0.92);
          backdrop-filter: blur(12px);
          -webkit-backdrop-filter: blur(12px);
          border-bottom: 1px solid var(--omni-rule, rgba(14, 10, 26, 0.1));
          display: grid;
          grid-template-columns: 240px 1fr 240px;
          align-items: center;
          padding: 10px 24px;
          gap: 20px;
          height: 52px;
        }
        .mr-brand {
          display: flex;
          align-items: center;
          gap: 10px;
          min-width: 0;
        }
        .mr-mark {
          font-family: "Fraunces", ui-serif, Georgia, serif;
          font-variation-settings: "opsz" 144, "wght" 500;
          font-size: 22px;
          color: var(--omni-ink, #0e0a1a);
          text-decoration: none;
          line-height: 1;
        }
        .mr-name {
          font-family: "Fraunces", ui-serif, Georgia, serif;
          font-variation-settings: "opsz" 24, "wght" 480;
          font-size: 13px;
          color: var(--omni-ink, #0e0a1a);
          text-decoration: none;
          letter-spacing: -0.005em;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .mr-v {
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 9px;
          color: var(--omni-mute, #8a7f6c);
          letter-spacing: 0.12em;
        }
        .mr-search-slot {
          display: flex;
          justify-content: center;
          min-width: 0;
        }
        .mr-user {
          display: flex;
          align-items: center;
          gap: 12px;
          justify-content: flex-end;
          font-family: "JetBrains Mono", ui-monospace, monospace;
          font-size: 10px;
          color: var(--omni-faint, #5a5242);
          letter-spacing: 0.06em;
          min-width: 0;
        }
        .mr-status, .mr-tenant {
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .mr-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: var(--omni-verdigris, #3e7a6b);
          box-shadow: 0 0 6px var(--omni-verdigris, #3e7a6b);
          flex-shrink: 0;
        }
        .mr-avatar {
          width: 24px;
          height: 24px;
          border-radius: 50%;
          background: linear-gradient(135deg, #c49a6c, #3e7a6b);
          border: 1px solid var(--omni-rule, rgba(14, 10, 26, 0.1));
          flex-shrink: 0;
        }

        @media (max-width: 840px) {
          .mr-topbar {
            grid-template-columns: auto 1fr auto;
            padding: 10px 14px;
          }
          .mr-name, .mr-v, .mr-status, .mr-tenant {
            display: none;
          }
        }
      `}</style>
    </header>
  );
}

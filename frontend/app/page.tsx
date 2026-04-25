"use client";
/**
 * Home — the hero search surface.
 *
 * Replaces the previous 14-tiles dashboard grid. The OmniBar in "hero" mode
 * IS the home: no sidebar fallback, no stat counters, no quick-links grid.
 *
 * Why "use client"? OmniBar handles client-side state (debounced query,
 * SWR fetches, keyboard navigation, intent classification). It cannot be a
 * Server Component. The wrapper here is intentionally minimal so the JS
 * bundle for the home page is the OmniBar itself plus its dependencies —
 * nothing more.
 *
 * Rollout: the previous tile-based home is preserved at /home-classic for
 * the duration of the rollout. Linked from the OmniBar's footer hint when
 * `?fallback=1` is passed. After 2 weeks, /home-classic can be removed
 * entirely.
 */
import { OmniBar } from "@/components/OmniBar/OmniBar";

export default function HomePage() {
  return <OmniBar mode="hero" />;
}

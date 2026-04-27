"use client";
/**
 * OmniBarProvider — global state and Cmd+K shortcut for the overlay mode.
 *
 * Place once inside layout.tsx:
 *
 *   <OmniBarProvider>
 *     <Topbar />
 *     <main>{children}</main>
 *   </OmniBarProvider>
 *
 * Then anywhere in the tree:
 *
 *   const { open, setOpen } = useOmniBar();
 *
 * Responsibilities:
 *   - Bind Cmd+K (Mac) / Ctrl+K (Linux/Win) to toggle the overlay
 *   - Bind Escape to close the overlay
 *   - Render <OmniBar mode="overlay"> at the provider level so it escapes
 *     any parent with overflow:hidden
 */
import { createContext, useContext, useEffect, useState, useCallback } from "react";
import type { ReactNode } from "react";
import { OmniBar } from "@/components/OmniBar/OmniBar";

interface OmniBarContextValue {
  open: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
}

const OmniBarContext = createContext<OmniBarContextValue>({
  open: false,
  setOpen: () => {},
  toggle: () => {},
});

export function OmniBarProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Cmd+K (Mac) or Ctrl+K (Linux/Windows) toggles the overlay.
      // We don't capture keystrokes inside form fields by default, but
      // Cmd+K is so commonly used as a global "open search" shortcut that
      // intercepting it everywhere is the expected behavior.
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape" && open) {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open]);

  return (
    <OmniBarContext.Provider value={{ open, setOpen, toggle }}>
      {children}
      <OmniBar mode="overlay" open={open} onOpenChange={setOpen} />
    </OmniBarContext.Provider>
  );
}

export function useOmniBar(): OmniBarContextValue {
  return useContext(OmniBarContext);
}

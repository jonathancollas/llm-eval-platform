"use client";
import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Cpu, Library, Activity, Trophy, Info,
         Dna, Shield, Gavel, Bot, Zap,
         Beaker, AlertCircle, Radio, Lock, FlaskConical, List,
         Menu, X, Rocket, LineChart, Layers, TestTubes, Search,
         Crosshair, GitBranch, BrainCircuit } from "lucide-react";
import { cn } from "@/lib/utils";
import { APP_VERSION } from "@/lib/config";
import { ThemeSwitcher } from "@/components/ThemeProvider";

// ── Évaluer — primary entry point ─────────────────────────────────────────────
const NAV_EVALUATE = [
  { href: "/evaluate",  label: "Evaluation Studio", icon: Rocket },
  { href: "/campaigns", label: "Run History",        icon: List },
];

// ── Analyser — post-eval insights ─────────────────────────────────────────────
const NAV_ANALYSE = [
  { href: "/dashboard",   label: "Dashboard",        icon: BarChart3 },
  { href: "/leaderboard", label: "Leaderboard",      icon: Trophy },
  { href: "/genome",      label: "Genomia",          icon: Dna },
  { href: "/judge",       label: "LLM Judge",        icon: Gavel },
  { href: "/agents",      label: "Agents",           icon: Bot },
  { href: "/vibe",        label: "Vibe Check",       icon: Zap, badge: "NEW" },
  { href: "/capabilities",  label: "Capability Intel", icon: BrainCircuit },
  { href: "/forecasting",       label: "Forecasting",        icon: LineChart },
  { href: "/frontier-metrics",  label: "Frontier Metrics",   icon: Crosshair },
];

// ── Opérer — production & compliance ──────────────────────────────────────────
const NAV_OPERATE = [
  { href: "/telemetry",        label: "Monitoring",      icon: Radio },
  { href: "/incidents",        label: "Incidents",       icon: AlertCircle },
  { href: "/policy",           label: "Compliance",      icon: Shield },
  { href: "/scenarios",        label: "Scenarios",       icon: Layers },
  { href: "/failure-patterns", label: "Failure Patterns", icon: GitBranch },
];

// ── Bibliothèque — primitives & reference ─────────────────────────────────────
const NAV_LIBRARY = [
  { href: "/models",      label: "Models",      icon: Cpu },
  { href: "/benchmarks",  label: "Benchmarks",  icon: Library },
  { href: "/evidence",    label: "Evidence",    icon: TestTubes },
  { href: "/research",    label: "Workspaces",  icon: Beaker },
  { href: "/methodology", label: "Methodology", icon: FlaskConical },
  { href: "/about",       label: "About",       icon: Info },
];

const MercurySymbol = () => (
  <svg width="38" height="38" viewBox="0 0 80 80" xmlns="http://www.w3.org/2000/svg">
    <text x="40" y="68" textAnchor="middle"
      fontFamily="system-ui, sans-serif" fontSize="72" fontWeight="900"
      stroke="#FF00FF" strokeWidth="12" strokeLinejoin="round"
      fill="none" opacity="0.08">☿</text>
    <text x="40" y="68" textAnchor="middle"
      fontFamily="system-ui, sans-serif" fontSize="72" fontWeight="900"
      stroke="#00EEFF" strokeWidth="5" strokeLinejoin="round"
      fill="none" opacity="0.45">☿</text>
    <text x="40" y="68" textAnchor="middle"
      fontFamily="system-ui, sans-serif" fontSize="72" fontWeight="900"
      stroke="#FF22AA" strokeWidth="1.5" strokeLinejoin="round"
      fill="none" opacity="0.85">☿</text>
    <text x="40" y="68" textAnchor="middle"
      fontFamily="system-ui, sans-serif" fontSize="72" fontWeight="900"
      fill="#1A0035">☿</text>
  </svg>
);

function NavSection({
  items,
  activeColor = "bg-slate-900 text-white",
  hoverColor = "hover:bg-slate-100 hover:text-slate-900",
  onLinkClick,
}: {
  items: { href: string; label: string; icon: React.ElementType; badge?: string }[];
  activeColor?: string;
  hoverColor?: string;
  onLinkClick?: () => void;
}) {
  const pathname = usePathname();
  return (
    <>
      {items.map(({ href, label, icon: Icon, badge }) => (
        <Link key={href} href={href} onClick={onLinkClick}
          className={cn(
            "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors",
            pathname === href || (href !== "/" && pathname.startsWith(href))
              ? `${activeColor} font-medium` : `text-slate-600 ${hoverColor}`
          )}>
          <Icon size={14} />{label}
          {badge && (
            <span className="ml-auto text-[8px] px-1.5 py-0.5 rounded-full bg-cyan-100 text-cyan-600 font-bold tracking-wide border border-cyan-200">
              {badge}
            </span>
          )}
        </Link>
      ))}
    </>
  );
}

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="px-3 pt-3 pb-0.5">
      <span className="text-[9px] font-bold tracking-widest uppercase text-slate-400">
        {label}
      </span>
    </div>
  );
}

function NavContent({ onLinkClick }: { onLinkClick?: () => void }) {
  const pathname = usePathname();
  const isRedbox = pathname.startsWith("/redbox");
  return (
    <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">

      {/* Overview — standalone top entry */}
      <Link href="/" onClick={onLinkClick}
        className={cn(
          "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors mb-1",
          pathname === "/" ? "bg-slate-900 text-white font-medium" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        )}>
        <Activity size={14} />Overview
      </Link>

      {/* ── ÉVALUER ── */}
      <div className="border-t border-slate-100 pt-1">
        <SectionLabel label="Évaluer" />
        {/* Evaluation Studio — primary CTA */}
        <Link href="/evaluate" onClick={onLinkClick}
          className={cn(
            "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors font-medium",
            pathname === "/evaluate" || pathname.startsWith("/evaluate")
              ? "bg-slate-900 text-white"
              : "text-slate-700 hover:bg-slate-100"
          )}>
          <Rocket size={14} />Evaluation Studio
        </Link>
        <NavSection items={NAV_EVALUATE.slice(1)} onLinkClick={onLinkClick} />
      </div>

      {/* ── ANALYSER ── */}
      <div className="border-t border-slate-100 pt-1">
        <SectionLabel label="Analyser" />
        <NavSection
          items={NAV_ANALYSE}
          activeColor="bg-violet-700 text-white"
          hoverColor="hover:bg-violet-50 hover:text-violet-700"
          onLinkClick={onLinkClick}
        />
      </div>

      {/* ── OPÉRER ── */}
      <div className="border-t border-slate-100 pt-1">
        <SectionLabel label="Opérer" />
        <NavSection
          items={NAV_OPERATE}
          activeColor="bg-amber-700 text-white"
          hoverColor="hover:bg-amber-50 hover:text-amber-700"
          onLinkClick={onLinkClick}
        />
        {/* The Red Room — restricted */}
        <Link
          href="/redbox"
          onClick={onLinkClick}
          className={cn(
            "group flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-all font-medium mt-0.5",
            isRedbox
              ? "bg-red-700 text-white shadow-md"
              : "text-red-700 hover:bg-red-700 hover:text-white border border-red-200"
          )}
        >
          <Lock size={13} className={cn(isRedbox ? "text-red-200" : "text-red-400 group-hover:text-red-200")} />
          <span>The Red Room</span>
          <span className={cn(
            "ml-auto text-[8px] px-1 py-0.5 rounded tracking-widest font-bold",
            isRedbox ? "bg-red-900 text-red-300" : "bg-red-100 text-red-500 group-hover:bg-red-900 group-hover:text-red-300"
          )}>RESTRICTED</span>
        </Link>
      </div>

      {/* ── BIBLIOTHÈQUE ── */}
      <div className="border-t border-slate-100 pt-1">
        <SectionLabel label="Bibliothèque" />
        <NavSection
          items={NAV_LIBRARY}
          activeColor="bg-teal-700 text-white"
          hoverColor="hover:bg-teal-50 hover:text-teal-700"
          onLinkClick={onLinkClick}
        />
      </div>
    </nav>
  );
}

export function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  // Close mobile nav on route change
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // Prevent body scroll when mobile drawer is open
  useEffect(() => {
    if (mobileOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [mobileOpen]);

  const closeMobile = () => setMobileOpen(false);

  return (
    <>
      {/* ── Desktop sidebar ─────────────────────────────── */}
      <aside className="hidden md:flex w-56 border-r border-slate-200 bg-white flex-col shrink-0">
        <Link href="/" className="px-4 py-4 border-b border-slate-100 hover:bg-slate-50 transition-colors group">
          <div className="flex items-center gap-3">
            <MercurySymbol />
            <div>
              <div className="font-bold text-slate-900 text-[10px] tracking-widest leading-tight group-hover:text-purple-700 transition-colors">
                MERCURY RETROGRADE
              </div>
              <div className="text-slate-400 mt-0.5 tracking-wide" style={{ fontSize: "8px" }}>
                an AI evaluation research OS, made with love by INESIA
              </div>
            </div>
          </div>
        </Link>

        <NavContent />

        <div className="p-3 border-t border-slate-100">
          <div className="flex items-center justify-between mb-1">
            <div className="text-slate-300" style={{ fontSize: "9px", letterSpacing: "1px" }}>
              ☿ {APP_VERSION}
            </div>
            <ThemeSwitcher />
          </div>
        </div>
      </aside>

      {/* ── Mobile top bar ──────────────────────────────── */}
      <header className="mobile-topbar md:hidden fixed top-0 left-0 right-0 z-40 h-14 bg-white border-b border-slate-200 flex items-center px-4 gap-3">
        <button
          onClick={() => setMobileOpen(true)}
          className="p-2 -ml-1 rounded-lg hover:bg-slate-100 text-slate-600 transition-colors"
          aria-label="Open navigation menu"
          aria-expanded={mobileOpen}
          aria-controls="mobile-nav-drawer"
        >
          <Menu size={20} />
        </button>
        <Link href="/" className="flex items-center gap-2.5 min-w-0">
          <MercurySymbol />
          <span className="font-bold text-slate-900 text-[10px] tracking-widest leading-tight truncate">
            MERCURY RETROGRADE
          </span>
        </Link>
        <div className="ml-auto shrink-0">
          <ThemeSwitcher />
        </div>
      </header>

      {/* ── Mobile drawer ───────────────────────────────── */}
      {mobileOpen && (
        <div
          id="mobile-nav-drawer"
          className="md:hidden fixed inset-0 z-50 flex"
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
        >
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/40"
            onClick={closeMobile}
            aria-hidden="true"
          />

          {/* Panel */}
          <aside className="relative w-72 max-w-[85vw] bg-white flex flex-col h-full shadow-xl">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
              <div className="flex items-center gap-2.5 min-w-0">
                <MercurySymbol />
                <div className="min-w-0">
                  <div className="font-bold text-slate-900 text-[10px] tracking-widest leading-tight">
                    MERCURY RETROGRADE
                  </div>
                  <div className="text-slate-400 mt-0.5 tracking-wide" style={{ fontSize: "8px" }}>
                    Mercury Research OS by INESIA
                  </div>
                </div>
              </div>
              <button
                onClick={closeMobile}
                className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition-colors shrink-0 ml-2"
                aria-label="Close menu"
              >
                <X size={16} />
              </button>
            </div>

            <NavContent onLinkClick={closeMobile} />

            <div className="p-3 border-t border-slate-100">
              <div className="flex items-center justify-between">
                <div className="text-slate-300" style={{ fontSize: "9px", letterSpacing: "1px" }}>
                  ☿ {APP_VERSION}
                </div>
                <ThemeSwitcher />
              </div>
            </div>
          </aside>
        </div>
      )}
    </>
  );
}

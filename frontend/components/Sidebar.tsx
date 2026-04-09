"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Cpu, Library, Rocket, Activity, Trophy, Info,
         Microscope, Dna, ShieldAlert, Shield, Gavel, Bot,
         Beaker, AlertCircle, Radio, TestTubes, Lock } from "lucide-react";
import { cn } from "@/lib/utils";
import { APP_NAME, APP_TAGLINE, APP_VERSION } from "@/lib/config";

const NAV_FOUNDATION = [
  { href: "/",           label: "Overview",       icon: Activity },
  { href: "/models",     label: "Models",          icon: Cpu },
  { href: "/benchmarks", label: "Benchmarks",      icon: Library },
];

const NAV_PHASE1 = [
  { href: "/campaigns",   label: "Campaigns",      icon: Rocket },
  { href: "/dashboard",   label: "Dashboard",      icon: BarChart3 },
  { href: "/leaderboard", label: "Leaderboard",    icon: Trophy },
  { href: "/policy",      label: "Compliance",     icon: Shield },
];

// Renamed: "Dynamic & Behavioral Eval" → "Behavioral Eval"
const NAV_PHASE2 = [
  { href: "/genome",  label: "Genomia",      icon: Dna },
  { href: "/judge",   label: "LLM Judge",    icon: Gavel },
  { href: "/agents",  label: "Agents",       icon: Bot },
];

// Phase 3 — Real World Eval (ALPHA)
const NAV_PHASE3 = [
  { href: "/evidence",   label: "Evidence (RCT)",   icon: TestTubes },
  { href: "/research",   label: "Workspaces",        icon: Beaker },
  { href: "/incidents",  label: "Incidents (SIX)",   icon: AlertCircle },
  { href: "/telemetry",  label: "Monitoring",         icon: Radio },
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

function NavSection({ items, activeColor = "bg-slate-900 text-white", hoverColor = "hover:bg-slate-100 hover:text-slate-900" }: {
  items: typeof NAV_FOUNDATION; activeColor?: string; hoverColor?: string;
}) {
  const pathname = usePathname();
  return (
    <>
      {items.map(({ href, label, icon: Icon }) => (
        <Link key={href} href={href}
          className={cn(
            "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors",
            pathname === href || (href !== "/" && pathname.startsWith(href))
              ? `${activeColor} font-medium` : `text-slate-600 ${hoverColor}`
          )}>
          <Icon size={14} />{label}
        </Link>
      ))}
    </>
  );
}

function PhaseHeader({ number, label, color, badge }: { number: number; label: string; color: string; badge?: string }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 mb-0.5">
      <span className={`w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold text-white ${color}`}>{number}</span>
      <span className={`text-[10px] font-semibold tracking-wider uppercase ${color.replace("bg-", "text-")}`}>{label}</span>
      {badge && (
        <span className={`text-[8px] px-1.5 py-0.5 rounded-full tracking-wide border ${color.replace("bg-", "border-").replace("700", "200").replace("600", "200")} ${color.replace("bg-", "text-").replace("700", "400").replace("600", "400")} bg-opacity-10`}>
          {badge}
        </span>
      )}
    </div>
  );
}

import { ThemeSwitcher } from "@/components/ThemeProvider";

export function Sidebar() {
  const pathname = usePathname();
  const isRedbox = pathname.startsWith("/redbox");

  return (
    <aside className="w-56 border-r border-slate-200 bg-white flex flex-col shrink-0">
      <Link href="/" className="px-4 py-4 border-b border-slate-100 hover:bg-slate-50 transition-colors group">
        <div className="flex items-center gap-3">
          <MercurySymbol />
          <div>
            <div className="font-bold text-slate-900 text-[10px] tracking-widest leading-tight group-hover:text-purple-700 transition-colors">
              EVAL RESEARCH OS
            </div>
            <div className="text-slate-400 mt-0.5 tracking-wide" style={{ fontSize: "8px" }}>
              made with love by INESIA
            </div>
          </div>
        </div>
      </Link>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        <NavSection items={NAV_FOUNDATION} />

        {/* Phase 1 — Static Evaluation */}
        <div className="pt-2 mt-2 border-t border-slate-100">
          <PhaseHeader number={1} label="Static Eval" color="bg-slate-700" />
          <NavSection items={NAV_PHASE1} />
        </div>

        {/* Phase 2 — Behavioral Eval (renamed from Dynamic & Behavioral Eval) */}
        <div className="pt-2 mt-2 border-t border-slate-100">
          <PhaseHeader number={2} label="Behavioral Eval" color="bg-cyan-700" badge="BETA" />
          <NavSection items={NAV_PHASE2} activeColor="bg-cyan-700 text-white" hoverColor="hover:bg-cyan-50 hover:text-cyan-700" />

          {/* The Red Room — replaces REDBOX */}
          <Link
            href="/redbox"
            className={cn(
              "group flex items-center gap-2.5 px-3 py-2 rounded-md text-[13px] transition-all font-medium mt-1",
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

        {/* Phase 3 — Real World Eval (ALPHA) */}
        <div className="pt-2 mt-2 border-t border-slate-100">
          <PhaseHeader number={3} label="Real World Eval" color="bg-violet-700" badge="ALPHA" />
          <NavSection items={NAV_PHASE3} activeColor="bg-violet-700 text-white" hoverColor="hover:bg-violet-50 hover:text-violet-700" />
        </div>

        {/* About */}
        <div className="pt-2 mt-1">
          <Link href="/about"
            className={cn(
              "flex items-center gap-2.5 px-3 py-1.5 rounded-md text-[13px] transition-colors",
              pathname === "/about" ? "bg-slate-900 text-white font-medium" : "text-slate-400 hover:bg-slate-50 hover:text-slate-600"
            )}>
            <Info size={14} />About
          </Link>
        </div>
      </nav>

      <div className="p-3 border-t border-slate-100">
        <div className="flex items-center justify-between mb-1">
          <div className="text-slate-300" style={{ fontSize: "9px", letterSpacing: "1px" }}>
            ☿ {APP_VERSION}
          </div>
          <ThemeSwitcher />
        </div>
      </div>
    </aside>
  );
}

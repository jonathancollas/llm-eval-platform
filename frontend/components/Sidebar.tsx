"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Cpu, Library, Rocket, Activity, Trophy, Info,
         Microscope, FlaskConical, ShieldAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV_MAIN = [
  { href: "/",           label: "Overview",       icon: Activity },
  { href: "/models",     label: "Models",          icon: Cpu },
  { href: "/benchmarks", label: "Benchmarks",      icon: Library },
  { href: "/campaigns",  label: "Campaigns",       icon: Rocket },
  { href: "/dashboard",  label: "Dashboard",       icon: BarChart3 },
  { href: "/leaderboard",label: "Leaderboard",     icon: Trophy },
  { href: "/genome",     label: "Failure Genome",  icon: FlaskConical },
  { href: "/about",      label: "About",           icon: Info },
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

export function Sidebar() {
  const pathname = usePathname();
  const isRedbox = pathname.startsWith("/redbox");

  return (
    <aside className="w-56 border-r border-slate-200 bg-white flex flex-col shrink-0">
      <Link href="/" className="px-4 py-4 border-b border-slate-100 hover:bg-slate-50 transition-colors group">
        <div className="flex items-center gap-3">
          <MercurySymbol />
          <div>
            <div className="font-bold text-slate-900 text-xs tracking-widest leading-tight group-hover:text-purple-700 transition-colors">
              MERCURY<br />RETROGRADE
            </div>
            <div className="text-slate-400 mt-0.5 tracking-wide" style={{ fontSize: "9px" }}>
              INESIA · AI EVALUATION
            </div>
          </div>
        </div>
      </Link>

      <nav className="flex-1 p-3 space-y-0.5 overflow-y-auto">
        {NAV_MAIN.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === href || (href !== "/" && pathname.startsWith(href))
                ? "bg-slate-900 text-white font-medium"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            )}>
            <Icon size={15} />{label}
          </Link>
        ))}

        {/* Analyzers — coming soon */}
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm cursor-not-allowed opacity-60 mt-1">
          <Microscope size={15} className="text-cyan-400" />
          <span className="text-cyan-400 font-medium">Analyzers</span>
          <span className="ml-auto text-[8px] bg-cyan-50 text-cyan-400 border border-cyan-200 px-1.5 py-0.5 rounded-full tracking-wide">
            IDLE
          </span>
        </div>

        {/* REDBOX — Red team lab */}
        <div className="pt-2 mt-2 border-t border-slate-100">
          <Link href="/redbox"
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors font-medium",
              isRedbox
                ? "bg-red-600 text-white"
                : "text-red-600 hover:bg-red-50 border border-red-200"
            )}>
            <ShieldAlert size={15} />
            <span>🔴 REDBOX</span>
            <span className={cn(
              "ml-auto text-[8px] px-1.5 py-0.5 rounded-full tracking-wide",
              isRedbox ? "bg-red-500 text-red-100" : "bg-red-50 text-red-400 border border-red-200"
            )}>
              BETA
            </span>
          </Link>
        </div>
      </nav>

      <div className="p-3 border-t border-slate-100 text-center">
        <div className="text-slate-300" style={{ fontSize: "9px", letterSpacing: "1px" }}>
          ☿ MR v0.4.0 · INESIA 2026
        </div>
      </div>
    </aside>
  );
}

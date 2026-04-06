"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Cpu, Library, Rocket, Activity, Trophy, Info, Microscope, FlaskConical } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/models", label: "Models", icon: Cpu },
  { href: "/benchmarks", label: "Benchmarks", icon: Library },
  { href: "/campaigns", label: "Campaigns", icon: Rocket },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/leaderboard", label: "Leaderboard", icon: Trophy },
  { href: "/about", label: "About", icon: Info },
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
    <text x="40" y="68" textAnchor="middle"
      fontFamily="system-ui, sans-serif" fontSize="72" fontWeight="900"
      fill="#CC44FF" opacity="0.18">☿</text>
  </svg>
);

export function Sidebar() {
  const pathname = usePathname();
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

      <nav className="flex-1 p-3 space-y-0.5">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link key={href} href={href}
            className={cn(
              "flex items-center gap-2.5 px-3 py-2 rounded-md text-sm transition-colors",
              pathname === href || pathname.startsWith(href + "/")
                ? "bg-slate-900 text-white font-medium"
                : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
            )}>
            <Icon size={15} />{label}
          </Link>
        ))}

        {/* Analyzers — coming soon */}
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-md text-sm cursor-not-allowed opacity-70 mt-1">
          <Microscope size={15} className="text-cyan-400" />
          <span className="text-cyan-400 font-medium">Analyzers</span>
          <span className="ml-auto text-xs bg-cyan-50 text-cyan-400 border border-cyan-200 px-1.5 py-0.5 rounded-full"
            style={{ fontSize: "8px", letterSpacing: "0.5px" }}>
            IDLE
          </span>
        </div>
      </nav>

      <div className="px-4 py-3 border-t border-slate-100">
        <p className="text-slate-400 tracking-wide" style={{ fontSize: "9px" }}>↺ MR · v0.2.0 · 2026</p>
      </div>
    </aside>
  );
}

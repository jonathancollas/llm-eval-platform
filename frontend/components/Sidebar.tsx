"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Cpu, Library, Rocket, Activity, Trophy } from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/models", label: "Models", icon: Cpu },
  { href: "/benchmarks", label: "Benchmarks", icon: Library },
  { href: "/campaigns", label: "Campaigns", icon: Rocket },
  { href: "/dashboard", label: "Dashboard", icon: BarChart3 },
  { href: "/leaderboard", label: "Leaderboard", icon: Trophy },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-56 border-r border-slate-200 bg-white flex flex-col shrink-0">
      <div className="px-5 py-5 border-b border-slate-100">
        <span className="font-semibold text-slate-900 text-sm">⚡ LLM Eval</span>
        <p className="text-xs text-slate-400 mt-0.5">INESIA · Plateforme d'évaluation</p>
      </div>
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
      </nav>
      <div className="px-4 py-3 border-t border-slate-100">
        <p className="text-xs text-slate-400">v0.2.0 — INESIA 2026</p>
      </div>
    </aside>
  );
}

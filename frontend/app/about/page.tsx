"use client";
import { PageHeader } from "@/components/PageHeader";
import Link from "next/link";
import { FileText, BookOpen, ExternalLink, Github, FlaskConical, Lock } from "lucide-react";
import { APP_NAME, APP_TAGLINE, APP_VERSION } from "@/lib/config";

const GITHUB_BASE = "https://github.com/jonathancollas/llm-eval-platform/blob/main";

const cards = [
  {
    icon: BookOpen,
    title: "README",
    description: "Getting started guide, tech stack, available benchmarks, Docker deployment.",
    href: `${GITHUB_BASE}/README.md`,
    label: "Read the README",
    color: "border-blue-200 bg-blue-50 hover:border-blue-300",
    iconColor: "text-blue-600",
    external: true,
  },
  {
    icon: FileText,
    title: "MANIFESTE",
    description: "INESIA mission, frontier evaluation methodology, benchmark governance, 2026-2027 roadmap.",
    href: `${GITHUB_BASE}/MANIFESTO.md`,
    label: "Read the Manifesto",
    color: "border-purple-200 bg-purple-50 hover:border-purple-300",
    iconColor: "text-purple-600",
    external: true,
  },
  {
    icon: FlaskConical,
    title: "Methodology Center",
    description: "Scientific foundations — papers, heuristics, capability vs. propensity, anti-sandbagging protocols.",
    href: "/methodology",
    label: "Open",
    color: "border-teal-200 bg-teal-50 hover:border-teal-300",
    iconColor: "text-teal-600",
    external: false,
  },
  {
    icon: Lock,
    title: "The Red Room",
    description: "Adversarial evaluation lab — prompt injection, goal drift, scheming detection, frontier red-teaming.",
    href: "/redbox",
    label: "Access",
    color: "border-red-200 bg-red-50 hover:border-red-300",
    iconColor: "text-red-600",
    external: false,
  },
  {
    icon: Github,
    title: "Code source",
    description: "Open source platform under dual Etalab 2.0 / Apache 2.0 license. Contributions welcome.",
    href: "https://github.com/jonathancollas/llm-eval-platform",
    label: "View on GitHub",
    color: "border-slate-200 bg-slate-50 hover:border-slate-300",
    iconColor: "text-slate-700",
    external: true,
  },
];

export default function AboutPage() {
  return (
    <div>
      <PageHeader
        title="About"
        description={`${APP_NAME} ${APP_VERSION} — ${APP_TAGLINE}`}
      />
      <div className="p-8 space-y-8 max-w-3xl">

        {/* Identity */}
        <div className="bg-gradient-to-br from-purple-50 to-blue-50 border border-purple-100 rounded-xl p-6">
          <div className="text-[10px] font-bold tracking-widest text-purple-400 uppercase mb-2">{APP_VERSION}</div>
          <h2 className="text-lg font-bold text-slate-900 mb-2">{APP_NAME}</h2>
          <p className="text-sm text-slate-600 leading-relaxed">
            The operating system for frontier AI safety evaluation — built by INESIA.
            Covers static benchmarking, behavioral diagnostics, continuous monitoring, adversarial red-teaming,
            and scientific evaluation methodology grounded in peer-reviewed research.
          </p>
        </div>

        {/* Doctrine */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h3 className="font-semibold text-slate-800 text-sm mb-3">INESIA Research Doctrine</h3>
          <div className="space-y-2 text-xs text-slate-600">
            {[
              ["🔭", "System-in-context evaluation", "Evaluate the system (model + tools + memory + orchestration), not the model in isolation."],
              ["⚖️", "Capability vs. Propensity", "Separate what a model CAN do (elicited max) from what it TENDS to do (operational distribution)."],
              ["🎭", "Anti-sandbagging", "Detect when models modify behaviour based on perceived evaluation context."],
              ["📡", "Continuous monitoring", "Pre-deployment evaluation is necessary but insufficient — post-deployment monitoring is a first-class obligation (NIST AI 800-4, 2026)."],
              ["🔬", "Benchmark validity", "Every score must be defensible — contamination-checked, expert-validated, reproducible."],
            ].map(([icon, title, desc]) => (
              <div key={title as string} className="flex gap-3 py-2 border-b border-slate-50 last:border-0">
                <span className="text-base shrink-0">{icon}</span>
                <div>
                  <div className="font-medium text-slate-800">{title as string}</div>
                  <div className="text-slate-500 mt-0.5">{desc as string}</div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Tech stack */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h3 className="font-semibold text-slate-800 text-sm mb-3">Tech Stack</h3>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              ["Frontend", "Next.js 14 · TypeScript · Tailwind CSS"],
              ["Backend", "FastAPI · SQLModel · SQLite"],
              ["Inference", "LiteLLM · OpenRouter · Ollama"],
              ["Eval harness", "lm-evaluation-harness (EleutherAI)"],
              ["Deployment", "Docker · Render"],
              ["License", "Etalab 2.0 / Apache 2.0"],
            ].map(([k, v]) => (
              <div key={k as string} className="bg-slate-50 rounded-lg p-2.5">
                <div className="text-slate-400 mb-0.5">{k as string}</div>
                <div className="font-medium text-slate-700">{v as string}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Links */}
        <div className="grid grid-cols-1 gap-3">
          {cards.map(({ icon: Icon, title, description, href, label, color, iconColor, external }) => (
            external ? (
              <a key={title} href={href} target="_blank" rel="noopener noreferrer"
                className={`flex items-start gap-4 border rounded-xl p-5 transition-colors ${color}`}>
                <Icon size={20} className={`${iconColor} mt-0.5 shrink-0`} />
                <div className="flex-1">
                  <div className="font-semibold text-slate-900 text-sm">{title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{description}</div>
                </div>
                <ExternalLink size={14} className="text-slate-400 mt-0.5 shrink-0" />
              </a>
            ) : (
              <Link key={title} href={href}
                className={`flex items-start gap-4 border rounded-xl p-5 transition-colors ${color}`}>
                <Icon size={20} className={`${iconColor} mt-0.5 shrink-0`} />
                <div className="flex-1">
                  <div className="font-semibold text-slate-900 text-sm">{title}</div>
                  <div className="text-xs text-slate-500 mt-0.5">{description}</div>
                </div>
              </Link>
            )
          ))}
        </div>

      </div>
    </div>
  );
}

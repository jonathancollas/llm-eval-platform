"use client";
import { PageHeader } from "@/components/PageHeader";
import { FileText, BookOpen, ExternalLink, Github } from "lucide-react";

const GITHUB_BASE = "https://github.com/jonathancollas/llm-eval-platform/blob/main";

const cards = [
  {
    icon: BookOpen,
    title: "README",
    description: "Guide de démarrage, stack technique, benchmarks disponibles, déploiement Docker.",
    href: `${GITHUB_BASE}/README.md`,
    label: "Lire le README",
    color: "border-blue-200 bg-blue-50 hover:border-blue-300",
    iconColor: "text-blue-600",
  },
  {
    icon: FileText,
    title: "MANIFESTE",
    description: "Mission de l'INESIA, méthodologie frontier, gouvernance des benchmarks, feuille de route 2026-2027.",
    href: `${GITHUB_BASE}/MANIFESTO.md`,
    label: "Lire le Manifeste",
    color: "border-purple-200 bg-purple-50 hover:border-purple-300",
    iconColor: "text-purple-600",
  },
  {
    icon: Github,
    title: "Code source",
    description: "Plateforme open source sous double licence Etalab 2.0 / Apache 2.0. Contributions bienvenues.",
    href: "https://github.com/jonathancollas/llm-eval-platform",
    label: "Voir sur GitHub",
    color: "border-slate-200 bg-slate-50 hover:border-slate-300",
    iconColor: "text-slate-700",
  },
];

export default function AboutPage() {
  return (
    <div>
      <PageHeader
        title="À propos"
        description="Mercury Retrograde — INESIA open evaluation platform."
      />
      <div className="p-8 max-w-3xl space-y-8">

        {/* Logo + tagline */}
        <div className="bg-white border border-slate-200 rounded-2xl p-8 flex flex-col items-center text-center gap-4">
          <svg width="120" height="120" viewBox="0 0 72 72" xmlns="http://www.w3.org/2000/svg">
            <defs><clipPath id="apc"><circle cx="36" cy="36" r="20"/></clipPath></defs>
            <ellipse cx="36" cy="36" rx="34" ry="8" fill="none" stroke="#ff00ff" strokeWidth="1.0" opacity="0.5" transform="rotate(-12 36 36)"/>
            <ellipse cx="36" cy="36" rx="26" ry="6" fill="none" stroke="#cc44ff" strokeWidth="1.4" opacity="0.65" transform="rotate(-12 36 36)"/>
            <circle cx="36" cy="36" r="20" fill="#1a0033"/>
            <circle cx="36" cy="36" r="20" fill="#3a0066" clipPath="url(#apc)"/>
            <ellipse cx="36" cy="30" rx="19" ry="5" fill="#cc00ff" opacity="0.2" clipPath="url(#apc)"/>
            <ellipse cx="36" cy="40" rx="19" ry="4" fill="#ff0088" opacity="0.18" clipPath="url(#apc)"/>
            <path d="M36 16 Q52 24 52 36 Q52 48 36 56 Q44 48 43 36 Q41 24 36 16Z" fill="#000022" opacity="0.5" clipPath="url(#apc)"/>
            <ellipse cx="28" cy="28" rx="9" ry="5" fill="#ff44ff" opacity="0.22" clipPath="url(#apc)"/>
            <ellipse cx="26" cy="26" rx="4" ry="2.5" fill="#ffffff" opacity="0.18" clipPath="url(#apc)"/>
            <circle cx="36" cy="36" r="20" fill="none" stroke="#ff00ff" strokeWidth="1.5" opacity="0.7"/>
            <path d="M10 22 Q22 12 36 14 Q50 12 62 22" fill="none" stroke="#00ffff" strokeWidth="1.6" strokeLinecap="round"/>
            <path d="M58 18 L62 22 L58 26" fill="none" stroke="#00ffff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M14 18 L10 22 L14 26" fill="none" stroke="#00ffff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          <div>
            <h1 className="text-2xl font-bold tracking-widest text-slate-900">MERCURY RETROGRADE</h1>
            <p className="text-sm text-slate-500 mt-1 tracking-wide">↺ MR · v0.2.0 · INESIA 2026</p>
          </div>
          <p className="text-sm text-slate-600 max-w-lg leading-relaxed">
            Open technical infrastructure for evaluating advanced AI models and systems,
            développée dans le cadre de la feuille de route INESIA 2026-2027.
          </p>
          <div className="flex items-center gap-4 text-xs text-slate-400">
            <span>SGDSN · DGE</span>
            <span>·</span>
            <span>ANSSI · Inria · LNE · PEReN</span>
            <span>·</span>
            <span>Etalab 2.0 / Apache 2.0</span>
          </div>
        </div>

        {/* Docs cards */}
        <div className="grid grid-cols-1 gap-4">
          {cards.map(({ icon: Icon, title, description, href, label, color, iconColor }) => (
            <a key={title} href={href} target="_blank" rel="noopener noreferrer"
              className={`border rounded-xl p-5 flex items-start gap-4 transition-colors group ${color}`}>
              <div className={`${iconColor} mt-0.5 shrink-0`}><Icon size={20} /></div>
              <div className="flex-1 min-w-0">
                <div className="font-semibold text-slate-900 mb-1">{title}</div>
                <p className="text-sm text-slate-600">{description}</p>
              </div>
              <div className="flex items-center gap-1 text-xs text-slate-400 group-hover:text-slate-600 transition-colors shrink-0 mt-1">
                {label} <ExternalLink size={12} className="ml-1"/>
              </div>
            </a>
          ))}
        </div>

        {/* Network */}
        <div className="bg-white border border-slate-200 rounded-xl p-5">
          <h2 className="font-medium text-slate-900 mb-3 text-sm">Réseau international</h2>
          <div className="grid grid-cols-2 gap-2 text-xs text-slate-500">
            {[
              ["METR", "Model Evaluation & Threat Research", "https://metr.org"],
              ["UK AISI", "AI Safety Institute, DSIT", "https://www.gov.uk/government/organisations/ai-safety-institute"],
              ["INAIMES", "International Network for Advanced AI Measurement", "https://www.gov.uk/government/publications/international-ai-safety-report"],
              ["EleutherAI", "lm-evaluation-harness", "https://github.com/EleutherAI/lm-evaluation-harness"],
            ].map(([name, desc, url]) => (
              <a key={name} href={url} target="_blank" rel="noopener noreferrer"
                className="flex flex-col p-3 rounded-lg border border-slate-100 hover:border-slate-200 hover:bg-slate-50 transition-colors">
                <span className="font-medium text-slate-700">{name}</span>
                <span className="text-slate-400 mt-0.5">{desc}</span>
              </a>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}

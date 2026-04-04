import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { SyncBanner } from "@/components/SyncBanner";

export const metadata: Metadata = {
  title: "LLM Eval Platform — INESIA",
  description: "Plateforme d'évaluation des modèles d'IA — INESIA",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body className="bg-slate-50 text-slate-900 antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-auto flex flex-col">
            <SyncBanner />
            <div className="flex-1">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}

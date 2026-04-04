import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { AutoSync } from "@/components/AutoSync";

export const metadata: Metadata = {
  title: "MR | Mercury Retrograde",
  description: "INESIA · AI Evaluation Platform — Mercury Retrograde",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='16' cy='16' r='16' fill='%231a0033'/><text x='16' y='22' text-anchor='middle' font-size='14' font-weight='bold' fill='%23ff00ff' font-family='system-ui'>MR</text></svg>"/>
      </head>
      <body className="bg-slate-50 text-slate-900 antialiased">
        <div className="flex h-screen overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-auto flex flex-col">
            <AutoSync />
            <div className="flex-1">{children}</div>
          </main>
        </div>
      </body>
    </html>
  );
}

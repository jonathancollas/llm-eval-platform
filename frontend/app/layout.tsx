import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { SyncBanner } from "@/components/SyncBanner";

export const metadata: Metadata = {
  title: "☿ Mercury Retrograde",
  description: "INESIA · AI Evaluation Platform — Mercury Retrograde",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <head>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' fill='%230D0020' rx='8'/><text x='32' y='54' text-anchor='middle' font-family='system-ui' font-size='52' font-weight='900' stroke='%2300EEFF' stroke-width='3' fill='%23CC44FF'>☿</text></svg>"/>
      </head>
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

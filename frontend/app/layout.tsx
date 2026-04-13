import type { Metadata } from "next";
import "./globals.css";
import { Sidebar } from "@/components/Sidebar";
import { SyncBanner } from "@/components/SyncBanner";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";

export const metadata: Metadata = {
  title: "EVAL RESEARCH OS (made with love by INESIA)",
  description: "INESIA · The operating system for frontier AI safety evaluation",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          rel="icon"
          href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><rect width='64' height='64' fill='%230D0020' rx='8'/><text x='32' y='54' text-anchor='middle' font-family='system-ui' font-size='52' font-weight='900' stroke='%2300EEFF' stroke-width='3' fill='%23CC44FF'>☿</text></svg>"
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.addEventListener('error', function(e) {
                console.error('[EVAL OS Runtime Error]', e.error);
              });
              window.addEventListener('unhandledrejection', function(e) {
                console.error('[EVAL OS Unhandled Promise]', e.reason);
              });
            `,
          }}
        />
      </head>
      <body className="bg-slate-50 text-slate-900 antialiased theme-light">
        <ThemeProvider>
          <div className="flex h-screen overflow-hidden pt-14 md:pt-0">
            <Sidebar />
            <main className="flex-1 overflow-auto flex flex-col">
              <SyncBanner />
              <AppErrorBoundary>
                <div className="flex-1">{children}</div>
              </AppErrorBoundary>
            </main>
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}

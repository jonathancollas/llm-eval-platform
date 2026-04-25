import type { Metadata } from "next";
import "./globals.css";
import { SyncBanner } from "@/components/SyncBanner";
import { ThemeProvider } from "@/components/ThemeProvider";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { Topbar } from "@/components/Topbar";
import { OmniBarProvider } from "@/components/OmniBar/OmniBarProvider";

export const metadata: Metadata = {
  title: "Mercury Retrograde — INESIA",
  description: "An observatory for frontier AI behavior.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <link
          rel="icon"
          href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'><text x='32' y='54' text-anchor='middle' font-family='system-ui' font-size='52' font-weight='900' fill='%230E0A1A'>☿</text></svg>"
        />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght,SOFT@0,9..144,100..900,30..100;1,9..144,100..900,30..100&family=Geist:wght@300..700&family=JetBrains+Mono:wght@400..600&display=swap"
          rel="stylesheet"
        />
        <script
          dangerouslySetInnerHTML={{
            __html: `
              window.addEventListener('error', function(e) {
                console.error('[Mercury Retrograde Runtime Error]', e.error);
              });
              window.addEventListener('unhandledrejection', function(e) {
                console.error('[Mercury Retrograde Unhandled Promise]', e.reason);
              });
            `,
          }}
        />
      </head>
      <body className="mr-body">
        <ThemeProvider>
          <OmniBarProvider>
            <Topbar />
            <SyncBanner />
            <AppErrorBoundary>
              <main className="mr-main">{children}</main>
            </AppErrorBoundary>
          </OmniBarProvider>
        </ThemeProvider>

        <style>{`
          /* Design tokens — observatory palette, audit §5.2 */
          :root {
            --omni-ink:        #0E0A1A;
            --omni-ink-2:      #1A1430;
            --omni-bone:       #F1ECE0;
            --omni-bone-2:     #E8E0D0;
            --omni-bone-3:     #D6CBB3;
            --omni-mute:       #8A7F6C;
            --omni-faint:      #5A5242;
            --omni-vermillion: #C9302C;
            --omni-mercury:    #C49A6C;
            --omni-verdigris:  #3E7A6B;
            --omni-rule:       rgba(14,10,26,0.10);
            --omni-rule-2:     rgba(14,10,26,0.06);
            --omni-grid:       rgba(14,10,26,0.035);
          }
          html, body { margin: 0; padding: 0; }
          .mr-body {
            font-family: "Geist", system-ui, sans-serif;
            font-weight: 350;
            font-size: 14px;
            line-height: 1.5;
            color: var(--omni-ink);
            background: var(--omni-bone);
            -webkit-font-smoothing: antialiased;
            min-height: 100vh;
          }
          .mr-main {
            min-height: calc(100vh - 52px);
          }
        `}</style>
      </body>
    </html>
  );
}

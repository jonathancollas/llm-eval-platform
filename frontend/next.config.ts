import type { NextConfig } from "next";

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";

function configuredApiOrigin(): string[] {
  try {
    const parsed = new URL(apiUrl);
    if (parsed.protocol === "http:" || parsed.protocol === "https:") {
      return [parsed.origin];
    }
  } catch {
    // Relative API URLs are covered by 'self'.
  }
  return [];
}

const connectSrc = Array.from(
  new Set([
    "'self'",
    "https://openrouter.ai",
    "https://api.lakera.ai",
    "https://llm-eval-backend-kqlh.onrender.com",
    ...configuredApiOrigin(),
  ])
).join(" ");

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-XSS-Protection", value: "1; mode=block" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Content-Security-Policy",
    value: [
      "default-src 'self'",
      "script-src 'self' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      `connect-src ${connectSrc}`,
      "frame-ancestors 'none'",
    ].join("; "),
  },
  {
    key: "Strict-Transport-Security",
    value: "max-age=31536000; includeSubDomains",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  compress: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
};
export default nextConfig;

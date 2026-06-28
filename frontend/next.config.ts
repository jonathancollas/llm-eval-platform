import type { NextConfig } from "next";

const connectSrc = new Set([
  "'self'",
  "https://openrouter.ai",
  "https://api.lakera.ai",
  "https://llm-eval-backend-kqlh.onrender.com",
]);

for (const apiUrl of [
  process.env.NEXT_PUBLIC_API_URL,
  "http://localhost:8000/api",
]) {
  if (!apiUrl) {
    continue;
  }

  try {
    connectSrc.add(new URL(apiUrl).origin);
  } catch {
    // Ignore malformed build-time values; the runtime fetch will surface that
    // configuration error without weakening the policy.
  }
}

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
      `connect-src ${Array.from(connectSrc).join(" ")}`,
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

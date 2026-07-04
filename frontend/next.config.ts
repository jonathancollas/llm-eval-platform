import type { NextConfig } from "next";

const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const configuredApiOrigin = (() => {
  try {
    return new URL(configuredApiUrl).origin;
  } catch {
    return null;
  }
})();
const connectSrc = [
  "'self'",
  "https://openrouter.ai",
  "https://api.lakera.ai",
  "https://llm-eval-backend-kqlh.onrender.com",
];

if (configuredApiOrigin && !connectSrc.includes(configuredApiOrigin)) {
  connectSrc.push(configuredApiOrigin);
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
      `connect-src ${connectSrc.join(" ")}`,
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

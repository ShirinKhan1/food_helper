import type { NextConfig } from "next";

const apiProxy = process.env.API_PROXY_TARGET?.trim();

const nextConfig: NextConfig = {
  output: "standalone",
  // Rewrites to the API can exceed the default proxy limit (~30s); chat + LLM may take 60–120s.
  experimental: {
    proxyTimeout: 180_000,
  },
  async rewrites() {
    if (!apiProxy) return [];
    const base = apiProxy.replace(/\/$/, "");
    return [
      { source: "/v1/:path*", destination: `${base}/v1/:path*` },
      { source: "/health", destination: `${base}/health` },
    ];
  },
};

export default nextConfig;

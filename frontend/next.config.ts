import type { NextConfig } from "next";

const staticExport = process.env.SONICSTREAM_STATIC === "1";

const nextConfig: NextConfig = {
  output: staticExport ? "export" : undefined,
  images: { unoptimized: true },
  async rewrites() {
    if (staticExport || process.env.NEXT_PUBLIC_API_URL) {
      return [];
    }
    const api = process.env.SONICSTREAM_API_PROXY || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/health", destination: `${api}/health` },
      { source: "/version", destination: `${api}/version` },
    ];
  },
};

export default nextConfig;

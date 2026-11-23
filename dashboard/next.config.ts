import type { NextConfig } from "next";
const config: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/lab/:path*",
        destination:
          (process.env.LAB_API_URL || "http://127.0.0.1:8810") + "/:path*",
      },
    ];
  },
  poweredByHeader: false,
};
export default config;

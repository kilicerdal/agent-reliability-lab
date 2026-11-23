import type { NextConfig } from "next";
const staticExport = process.env.LAB_STATIC_EXPORT === "1";
const config: NextConfig = staticExport
  ? {
      output: "export",
      trailingSlash: true,
      basePath: process.env.NEXT_PUBLIC_LAB_BASE_PATH || "",
      poweredByHeader: false,
    }
  : {
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

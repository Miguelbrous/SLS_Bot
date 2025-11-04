import { BundleAnalyzerPlugin } from "webpack-bundle-analyzer";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    optimizePackageImports: ["lightweight-charts", "react"],
  },
  webpack: (config, { isServer }) => {
    if (process.env.ANALYZE === "true" && !isServer) {
      config.plugins.push(
        new BundleAnalyzerPlugin({
          analyzerMode: "static",
          reportFilename: "bundle-report.html",
          openAnalyzer: false,
        })
      );
    }
    return config;
  },
};

export default nextConfig;

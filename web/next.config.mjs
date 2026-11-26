/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  serverExternalPackages: ["ws"],
  // Inlined at build time. Empty means lib/pipeline.ts uses its default.
  env: { GRAPH_API_VERSION: process.env.GRAPH_API_VERSION ?? "" },
};

export default nextConfig;

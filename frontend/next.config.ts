import type { NextConfig } from "next";
import CopyWebpackPlugin from "copy-webpack-plugin";
import path from "node:path";
import webpack from "webpack";

const cesiumSource = path.dirname(require.resolve("cesium/package.json"));
const cesiumBuild = path.join(cesiumSource, "Build", "Cesium");
const cesiumBaseUrl = "/_next/static/cesium";
const backendUrl = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  transpilePackages: ["cesium"],
  webpack(config) {
    config.plugins ??= [];
    config.plugins.push(
      new CopyWebpackPlugin({
        patterns: ["Workers", "Assets", "Widgets", "ThirdParty"].map(
          (directory) => ({
            from: path.join(cesiumBuild, directory),
            to: path.join("static", "cesium", directory),
            noErrorOnMissing: false,
          }),
        ),
      }),
      new webpack.DefinePlugin({
        CESIUM_BASE_URL: JSON.stringify(cesiumBaseUrl),
      }),
    );

    return config;
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

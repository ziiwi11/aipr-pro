import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  root: resolve(__dirname, "src"),
  // 增量脚本放在 src/public，Vite 会原样复制到 dist 根目录
  publicDir: resolve(__dirname, "src/public"),
  base: "./",
  // 测试配置：源码在 src/ 下，测试文件用 *.test.ts
  test: {
    root: resolve(__dirname),
    environment: "happy-dom",
    include: ["src/**/*.test.ts"],
    globals: true,
  },
  build: {
    // 输出到 app/dist，与现有 index.html 引用路径保持一致
    outDir: resolve(__dirname, "../dist"),
    emptyOutDir: false, // 保留增量脚本（aipr-ai-outreach.js 等）
    assetsDir: "assets",
    rollupOptions: {
      input: resolve(__dirname, "src/index.html"),
      output: {
        // 固定文件名，避免 electron/main.cjs 里硬编码的 hash 失效
        entryFileNames: "assets/app.js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name].[ext]",
      },
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  preview: {
    // electron/main.cjs 在非打包模式下加载 http://127.0.0.1:4173
    port: 4173,
    strictPort: true,
  },
});

import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const projectRoot = fileURLToPath(new URL(".", import.meta.url));

const resolveManualChunk = (id) => {
  if (!id.includes("node_modules")) return undefined;
  if (id.includes("mermaid")) return "mermaid";
  if (
    id.includes("react-syntax-highlighter")
  ) {
    return "code-highlight";
  }
  if (
    id.includes("remark-math")
    || id.includes("rehype-katex")
    || id.includes("/katex/")
  ) {
    return "markdown-rich";
  }
  if (id.includes("lucide-react")) return "icons";
  return undefined;
};

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, projectRoot, "");
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:18011";

  return {
    plugins: [react(), tailwindcss()],

    optimizeDeps: {
      include: ["react", "react-dom", "lucide-react", "react-router-dom"],
    },

    server: {
      host: "0.0.0.0",
      port: 5173,
      strictPort: true,
      allowedHosts: [
        "qianxiaanran.mynatapp.cc",
        ".mynatapp.cc",
        ".natapp.cc",
        "localhost",
        "127.0.0.1",
      ],
      cors: true,
      hmr: {
        host: "qianxiaanran.mynatapp.cc",
        protocol: "ws",
        clientPort: 80,
      },
      proxy: {
        "/api": {
          target: apiProxyTarget,
          changeOrigin: true,
          secure: false,
        },
      },
      watch: {
        usePolling: true,
        interval: 1000,
      },
    },

    build: {
      rollupOptions: {
        output: {
          manualChunks: resolveManualChunk,
        },
      },
    },
  };
});

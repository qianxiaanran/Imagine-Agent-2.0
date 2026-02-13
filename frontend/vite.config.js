import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],

  // 优化依赖预构建，防止部分依赖在网络慢时加载失败
  optimizeDeps: {
    include: ['react', 'react-dom', 'lucide-react', 'react-router-dom'],
  },

  server: {
    // 1. 允许局域网和公网 IP 访问绑定
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,

    // 2. 安全列表：允许你的穿透域名访问
    allowedHosts: [
      "qianxiaanran.mynatapp.cc",
      ".mynatapp.cc",
      ".natapp.cc",
      "localhost",
      "127.0.0.1"
    ],

    cors: true,

    // 3. ⭐ 核心修复：热更新 (HMR) 专用配置
    // 内网穿透时，浏览器必须知道去连接"公网域名"，而不是 localhost
    hmr: {
      host: "qianxiaanran.mynatapp.cc", // 强制指定你的公网域名
      protocol: "ws",                   // 默认为 ws，如果你配置了 https 证书则改为 wss
      clientPort: 80,                   // 告诉浏览器："WebSocket 请连到公网的 80 端口" (因为 Natapp 免费版通常是 80)
      // 如果 Natapp 映射的是 https (443)，请把 clientPort 改为 443
    },

    // 4. API 反向代理 (保持你原有的)
    proxy: {
      "/api": {
        target: "http://127.0.0.1:18000",
        changeOrigin: true,
        secure: false,
      }
    },

    // 5. 增加轮询策略 (可选，增强稳定性)
    watch: {
      usePolling: true,
      interval: 1000,
    }
  },

  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          markdown: [
            'react-markdown',
            'remark-gfm',
            'remark-math',
            'rehype-katex',
            'react-syntax-highlighter',
            'katex'
          ],
          mermaid: ['mermaid'],
          icons: ['lucide-react']
        }
      }
    }
  }
});

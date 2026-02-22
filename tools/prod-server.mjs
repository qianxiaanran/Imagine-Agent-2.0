import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";
import https from "node:https";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const distRoot = path.join(repoRoot, "frontend", "dist");

const PORT = Number(process.env.PORT || 8080);
const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:18011";
const apiUrl = new URL(API_TARGET);

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".map": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
};

function setNoCacheForHtml(res, filePath) {
  if (path.extname(filePath).toLowerCase() === ".html") {
    res.setHeader("Cache-Control", "no-store, max-age=0");
  } else {
    res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
  }
}

function sendFile(res, filePath) {
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.statusCode = 500;
      res.end("Internal Server Error");
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.setHeader("Content-Type", MIME_TYPES[ext] || "application/octet-stream");
    setNoCacheForHtml(res, filePath);
    res.statusCode = 200;
    res.end(data);
  });
}

function resolveSafePath(urlPath) {
  const decoded = decodeURIComponent(urlPath.split("?")[0]);
  const normalized = path.normalize(decoded).replace(/^(\.\.[/\\])+/, "");
  const finalPath = path.join(distRoot, normalized);
  if (!finalPath.startsWith(distRoot)) {
    return null;
  }
  return finalPath;
}

function proxyApi(req, res) {
  const client = apiUrl.protocol === "https:" ? https : http;
  const options = {
    protocol: apiUrl.protocol,
    hostname: apiUrl.hostname,
    port: apiUrl.port || (apiUrl.protocol === "https:" ? 443 : 80),
    method: req.method,
    path: req.url,
    headers: {
      ...req.headers,
      host: apiUrl.host,
      connection: "close",
    },
  };

  const proxyReq = client.request(options, (proxyRes) => {
    res.writeHead(proxyRes.statusCode || 502, proxyRes.headers);
    proxyRes.pipe(res, { end: true });
  });

  proxyReq.on("error", (err) => {
    res.statusCode = 502;
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(JSON.stringify({ error: "Bad Gateway", detail: err.message }));
  });

  req.pipe(proxyReq, { end: true });
}

if (!fs.existsSync(distRoot)) {
  console.error(`[prod-server] Missing dist folder: ${distRoot}`);
  console.error("[prod-server] Run: cd frontend && npm run build");
  process.exit(1);
}

const server = http.createServer((req, res) => {
  const urlPath = req.url || "/";

  if (urlPath.startsWith("/api/")) {
    proxyApi(req, res);
    return;
  }

  const safePath = resolveSafePath(urlPath === "/" ? "/index.html" : urlPath);
  if (!safePath) {
    res.statusCode = 403;
    res.end("Forbidden");
    return;
  }

  fs.stat(safePath, (err, stat) => {
    if (!err && stat.isFile()) {
      sendFile(res, safePath);
      return;
    }

    const indexPath = path.join(distRoot, "index.html");
    sendFile(res, indexPath);
  });
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`[prod-server] listening on http://0.0.0.0:${PORT}`);
  console.log(`[prod-server] proxy /api -> ${API_TARGET}`);
});

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import http from "node:http";
import https from "node:https";
import zlib from "node:zlib";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const distRoot = path.join(repoRoot, "frontend", "dist");

function readEnv(...keys) {
  for (const key of keys) {
    const raw = process.env[key];
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (value) return value;
  }
  return undefined;
}

const PORT = Number(readEnv("PORT") || 8080);
const HOST = readEnv("FRONTEND_HOST", "HOST") || "127.0.0.1";
const API_TARGET = readEnv("API_TARGET") || "http://127.0.0.1:18011";
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

const COMPRESSIBLE_EXTENSIONS = new Set([
  ".html",
  ".js",
  ".css",
  ".json",
  ".svg",
  ".txt",
  ".map",
]);
const COMPRESSION_MIN_BYTES = 1024;
const MAX_COMPRESSION_CACHE_ENTRIES = 96;
const compressionCache = new Map();

function buildEtag(stat) {
  return `W/"${stat.size.toString(16)}-${Math.trunc(stat.mtimeMs).toString(16)}"`;
}

function setCacheHeaders(res, filePath, stat) {
  const ext = path.extname(filePath).toLowerCase();
  res.setHeader("Content-Type", MIME_TYPES[ext] || "application/octet-stream");
  res.setHeader("Last-Modified", stat.mtime.toUTCString());
  res.setHeader("ETag", buildEtag(stat));
  if (COMPRESSIBLE_EXTENSIONS.has(ext)) {
    res.setHeader("Vary", "Accept-Encoding");
  }

  if (ext === ".html") {
    res.setHeader("Cache-Control", "no-cache, max-age=0, must-revalidate");
  } else {
    res.setHeader("Cache-Control", "public, max-age=31536000, immutable");
  }
}

function isRequestFresh(req, stat) {
  const etag = buildEtag(stat);
  const requestIfNoneMatch = req.headers["if-none-match"];
  if (typeof requestIfNoneMatch === "string" && requestIfNoneMatch.trim() === etag) {
    return true;
  }

  const requestIfModifiedSince = req.headers["if-modified-since"];
  if (typeof requestIfModifiedSince === "string") {
    const modifiedSince = Date.parse(requestIfModifiedSince);
    if (!Number.isNaN(modifiedSince) && Math.trunc(stat.mtimeMs) <= modifiedSince) {
      return true;
    }
  }

  return false;
}

function getPreferredEncoding(req, filePath, stat) {
  const ext = path.extname(filePath).toLowerCase();
  if (!COMPRESSIBLE_EXTENSIONS.has(ext)) return null;
  if ((stat?.size || 0) < COMPRESSION_MIN_BYTES) return null;

  const acceptEncoding = String(req.headers["accept-encoding"] || "").toLowerCase();
  if (acceptEncoding.includes("br")) return "br";
  if (acceptEncoding.includes("gzip")) return "gzip";
  return null;
}

function getCompressedPayload(filePath, stat, encoding) {
  const cacheKey = `${filePath}:${stat.size}:${Math.trunc(stat.mtimeMs)}:${encoding}`;
  const cached = compressionCache.get(cacheKey);
  if (cached) return cached;

  const source = fs.readFileSync(filePath);
  const buffer = encoding === "br"
    ? zlib.brotliCompressSync(source, {
        params: {
          [zlib.constants.BROTLI_PARAM_QUALITY]: 5,
        },
      })
    : zlib.gzipSync(source, { level: 6 });

  compressionCache.set(cacheKey, buffer);
  while (compressionCache.size > MAX_COMPRESSION_CACHE_ENTRIES) {
    const oldestKey = compressionCache.keys().next().value;
    if (!oldestKey) break;
    compressionCache.delete(oldestKey);
  }
  return buffer;
}

function sendFile(req, res, filePath, stat) {
  setCacheHeaders(res, filePath, stat);

  if (isRequestFresh(req, stat)) {
    res.statusCode = 304;
    res.end();
    return;
  }

  const preferredEncoding = getPreferredEncoding(req, filePath, stat);
  if (preferredEncoding) {
    const payload = getCompressedPayload(filePath, stat, preferredEncoding);
    res.statusCode = 200;
    res.setHeader("Content-Encoding", preferredEncoding);
    res.setHeader("Content-Length", String(payload.length));
    res.end(req.method === "HEAD" ? undefined : payload);
    return;
  }

  res.statusCode = 200;
  res.setHeader("Content-Length", String(stat.size));
  if (req.method === "HEAD") {
    res.end();
    return;
  }

  const stream = fs.createReadStream(filePath);
  stream.on("error", () => {
    if (!res.headersSent) {
      res.statusCode = 500;
    }
    res.end("Internal Server Error");
  });
  stream.pipe(res);
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
      sendFile(req, res, safePath, stat);
      return;
    }

    const indexPath = path.join(distRoot, "index.html");
    fs.stat(indexPath, (indexErr, indexStat) => {
      if (indexErr || !indexStat.isFile()) {
        res.statusCode = 500;
        res.end("Internal Server Error");
        return;
      }
      sendFile(req, res, indexPath, indexStat);
    });
  });
});

server.keepAliveTimeout = 65_000;
server.headersTimeout = 66_000;

server.on("error", (err) => {
  console.error(`[prod-server] failed to listen on http://${HOST}:${PORT}`);
  if (err?.code === "EADDRINUSE") {
    console.error("[prod-server] The port is already in use. Set PORT to a free port and retry.");
  } else if (err?.code === "EACCES") {
    console.error("[prod-server] Permission denied while binding the socket. Try FRONTEND_HOST=127.0.0.1 or use a different PORT.");
  } else if (err?.message) {
    console.error(`[prod-server] ${err.message}`);
  }
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  console.log(`[prod-server] listening on http://${HOST}:${PORT}`);
  console.log(`[prod-server] proxy /api -> ${API_TARGET}`);
});

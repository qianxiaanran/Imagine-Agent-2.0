const GENERIC_AVATAR_TEXTS = new Set([
  "avatar",
  "user",
  "photo",
  "image",
  "default",
  "null",
  "undefined",
]);

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

const isLoopbackHost = (host = "") => {
  const normalized = String(host).trim().toLowerCase();
  if (!normalized) return false;
  if (LOOPBACK_HOSTS.has(normalized)) return true;
  return normalized.startsWith("127.");
};

const isBrowser = () => typeof window !== "undefined" && !!window.location;

const currentHostIsLoopback = () => {
  if (!isBrowser()) return true;
  return isLoopbackHost(window.location.hostname);
};

const tryParseUrl = (value) => {
  try {
    return new URL(value);
  } catch {
    return null;
  }
};

const pushUnique = (list, value) => {
  if (typeof value !== "string") return;
  const trimmed = value.trim();
  if (!trimmed) return;
  if (!list.includes(trimmed)) list.push(trimmed);
};

export const isAvatarImageSource = (value) => {
  if (typeof value !== "string") return false;
  const src = value.trim();
  if (!src) return false;

  if (src.startsWith("blob:")) return true;
  if (src.startsWith("data:image/")) return true;
  if (src.startsWith("/")) return true;
  if (/^https?:\/\//i.test(src)) return true;
  if (/^[a-z0-9][a-z0-9._/-]*\.(png|jpe?g|webp|gif|bmp|svg)(\?.*)?$/i.test(src)) return true;

  return false;
};

export const extractAvatarUrl = (payload) => {
  if (!payload) return "";
  if (typeof payload === "string") return payload.trim();
  if (typeof payload !== "object") return "";

  const direct =
    payload.avatar_url ||
    payload.avatarUrl ||
    payload.url ||
    payload.publicUrl ||
    payload.publicURL ||
    payload.public_url ||
    payload.signedURL ||
    payload.signedUrl ||
    payload.signed_url ||
    payload.href;

  if (typeof direct === "string" && direct.trim()) return direct.trim();
  if (direct && typeof direct === "object") {
    const nestedDirect = extractAvatarUrl(direct);
    if (nestedDirect) return nestedDirect;
  }

  if (payload.data) {
    const nestedData = extractAvatarUrl(payload.data);
    if (nestedData) return nestedData;
  }

  return "";
};

const buildLoopbackFallbackSources = (src) => {
  const parsed = tryParseUrl(src);
  if (!parsed) return [];
  if (!/^https?:$/i.test(parsed.protocol)) return [];
  if (!isLoopbackHost(parsed.hostname)) return [];
  if (!isBrowser() || currentHostIsLoopback()) return [];

  const fallbacks = [];
  const pathnameAndQuery = `${parsed.pathname}${parsed.search}`;

  const publicSupabaseUrl =
    typeof import.meta !== "undefined" &&
    import.meta.env &&
    typeof import.meta.env.VITE_SUPABASE_PUBLIC_URL === "string"
      ? import.meta.env.VITE_SUPABASE_PUBLIC_URL.trim()
      : "";

  if (publicSupabaseUrl) {
    const parsedPublic = tryParseUrl(publicSupabaseUrl);
    if (parsedPublic) {
      pushUnique(fallbacks, `${parsedPublic.origin}${pathnameAndQuery}`);
    }
  }

  pushUnique(fallbacks, `${window.location.origin}${pathnameAndQuery}`);

  const sameHostWithOriginalPort = `${window.location.protocol}//${window.location.hostname}${
    parsed.port ? `:${parsed.port}` : ""
  }${pathnameAndQuery}`;
  pushUnique(fallbacks, sameHostWithOriginalPort);

  return fallbacks;
};

export const getAvatarCandidates = (value) => {
  if (typeof value !== "string") return [];
  const src = value.trim();
  if (!src || !isAvatarImageSource(src)) return [];

  const candidates = [];
  pushUnique(candidates, src);
  buildLoopbackFallbackSources(src).forEach((item) => pushUnique(candidates, item));
  return candidates;
};

export const getPreferredAvatarSource = (value) => {
  const src = typeof value === "string" ? value : extractAvatarUrl(value);
  const candidates = getAvatarCandidates(src);
  if (!candidates.length) return "";
  if (!isBrowser() || currentHostIsLoopback()) return candidates[0];

  const nonLoopback = candidates.find((item) => {
    const parsed = tryParseUrl(item);
    return !(parsed && isLoopbackHost(parsed.hostname));
  });
  return nonLoopback || candidates[0];
};

const getLeadingChar = (value) => {
  if (!value) return "";
  const text = String(value).trim();
  if (!text) return "";
  const first = Array.from(text)[0];
  return first ? first.toUpperCase() : "";
};

export const getAvatarFallback = (avatar, name = "") => {
  const raw = typeof avatar === "string" ? avatar.trim() : "";

  if (raw && !isAvatarImageSource(raw)) {
    const normalized = raw.toLowerCase();
    if (!GENERIC_AVATAR_TEXTS.has(normalized) && raw.length <= 2) {
      return raw.toUpperCase();
    }
  }

  return getLeadingChar(name) || "U";
};

export const appendCacheBuster = (url) => {
  if (typeof url !== "string") return "";
  const trimmed = url.trim();
  if (!trimmed) return "";
  const separator = trimmed.includes("?") ? "&" : "?";
  return `${trimmed}${separator}t=${Date.now()}`;
};

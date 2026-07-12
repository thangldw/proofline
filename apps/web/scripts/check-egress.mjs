import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, extname, join, relative, resolve } from "node:path";

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const TEXT_EXTENSIONS = new Set([
  ".css",
  ".html",
  ".js",
  ".mjs",
  ".json",
  ".svg",
  ".ts",
  ".tsx",
]);
const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function isApprovedAbsoluteUrl(rawUrl) {
  try {
    const url = new URL(rawUrl);
    if (LOOPBACK_HOSTS.has(url.hostname)) return true;
    if (url.hostname === "www.w3.org") return true;
    return (
      url.hostname === "reactjs.org" &&
      url.pathname === "/docs/error-decoder.html"
    );
  } catch {
    return false;
  }
}

export function findDisallowedUrls(text) {
  const findings = [];
  const absoluteUrlPattern = /\b(?:https?|wss?):\/\/[^\s"'<>`)}]+/giu;
  const protocolRelativeAssetPattern =
    /(?:url\(\s*|(?:src|href)\s*=\s*["']|(?:fetch|WebSocket|EventSource)\(\s*["'])\/\/[^\s"'<>`)]+/giu;

  for (const match of text.matchAll(absoluteUrlPattern)) {
    const rawUrl = match[0].replace(/[.,;:]$/u, "");
    if (!isApprovedAbsoluteUrl(rawUrl)) {
      findings.push({ index: match.index, url: rawUrl });
    }
  }
  for (const match of text.matchAll(protocolRelativeAssetPattern)) {
    const start = match[0].indexOf("//");
    findings.push({ index: match.index + start, url: match[0].slice(start) });
  }
  return findings;
}

function collectFiles(path) {
  if (!existsSync(path)) return [];
  if (statSync(path).isFile()) {
    if (/\.(?:test|spec)\.[cm]?[jt]sx?$/u.test(path)) return [];
    return TEXT_EXTENSIONS.has(extname(path)) ? [path] : [];
  }
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = join(path, entry.name);
    return entry.isDirectory() ? collectFiles(child) : collectFiles(child);
  });
}

function lineAt(text, index) {
  return text.slice(0, index).split("\n").length;
}

export function scanWebTree(root = WEB_ROOT) {
  const targets = [join(root, "src"), join(root, "index.html"), join(root, "vite.config.ts")];
  if (existsSync(join(root, "dist"))) targets.push(join(root, "dist"));

  return targets.flatMap(collectFiles).flatMap((file) => {
    const text = readFileSync(file, "utf8");
    return findDisallowedUrls(text).map((finding) => ({
      file: relative(root, file),
      line: lineAt(text, finding.index),
      url: finding.url,
    }));
  });
}

function main() {
  const findings = scanWebTree();
  if (findings.length === 0) {
    console.log("Egress check passed: no unapproved external URLs found.");
    return;
  }
  console.error("Egress check failed: unapproved external URLs found:");
  for (const finding of findings) {
    console.error(`  ${finding.file}:${finding.line} ${finding.url}`);
  }
  process.exitCode = 1;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}

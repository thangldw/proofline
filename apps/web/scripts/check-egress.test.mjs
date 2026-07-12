import assert from "node:assert/strict";
import test from "node:test";

import { findDisallowedUrls } from "./check-egress.mjs";

test("rejects external asset and API URLs", () => {
  const text = [
    "@import url('https://fonts.googleapis.com/css?family=Example');",
    'fetch("https://telemetry.example.test/collect")',
    '<img src="//cdn.example.test/logo.svg">',
  ].join("\n");

  assert.deepEqual(
    findDisallowedUrls(text).map(({ url }) => url),
    [
      "https://fonts.googleapis.com/css?family=Example",
      "https://telemetry.example.test/collect",
      "//cdn.example.test/logo.svg",
    ],
  );
});

test("allows relative and loopback API URLs", () => {
  const text = [
    'fetch("/api/v1/sources")',
    'const api = "http://127.0.0.1:8000";',
    'const local = "http://localhost:5173";',
    'const ipv6 = "ws://[::1]:8080";',
  ].join("\n");

  assert.deepEqual(findDisallowedUrls(text), []);
});

test("allows inert standards namespaces and React production diagnostics", () => {
  const text = [
    'const svgNamespace = "http://www.w3.org/2000/svg";',
    'const xlinkNamespace = "http://www.w3.org/1999/xlink";',
    'const decoder = "https://reactjs.org/docs/error-decoder.html?invariant=31";',
  ].join("\n");

  assert.deepEqual(findDisallowedUrls(text), []);
});

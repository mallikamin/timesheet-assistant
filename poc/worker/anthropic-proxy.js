/**
 * Cloudflare Worker — Anthropic API proxy.
 *
 * Render's free-tier outbound IPs land on Cloudflare's bot-challenge list,
 * so direct Render -> api.anthropic.com calls return Cloudflare's HTML
 * challenge page instead of JSON. Cloudflare Workers egress from
 * Cloudflare's own network, which is not challenged by Cloudflare's WAF
 * in front of Anthropic.
 *
 * Deploy:
 *   1. Cloudflare dashboard -> Workers & Pages -> Create -> Hello World
 *   2. Replace the default code with this file's contents -> Save & Deploy
 *   3. Worker -> Settings -> Variables and Secrets -> Add secret
 *      Name: PROXY_SECRET   Value: <generate a long random string>
 *   4. On Render, set env vars:
 *        ANTHROPIC_BASE_URL=https://<worker-name>.<account>.workers.dev
 *        ANTHROPIC_PROXY_SECRET=<same value as PROXY_SECRET>
 *
 * The Anthropic Python SDK's `base_url` argument routes every /v1/* call
 * through this Worker. We preserve method, path, query, headers, and body,
 * and stream SSE responses untouched.
 */

const UPSTREAM_HOST = "api.anthropic.com";

// Strip Cloudflare-injected and hop-by-hop headers before forwarding.
// "x-proxy-secret" is consumed here, not forwarded.
const STRIP_HEADERS = new Set([
  "host",
  "cf-connecting-ip",
  "cf-ipcountry",
  "cf-ray",
  "cf-visitor",
  "cf-ew-via",
  "cf-worker",
  "cdn-loop",
  "x-forwarded-for",
  "x-forwarded-proto",
  "x-real-ip",
  "x-proxy-secret",
]);

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Health check that doesn't require the secret — lets you curl the
    // Worker URL and confirm it's deployed before wiring up Render.
    if (url.pathname === "/__proxy_health") {
      return new Response(
        JSON.stringify({ status: "ok", upstream: UPSTREAM_HOST }),
        { headers: { "content-type": "application/json" } },
      );
    }

    // Shared-secret gate — prevents this from becoming an open Anthropic
    // relay anyone can burn our CF quota on. PROXY_SECRET is set in the
    // Worker's Variables and Secrets panel.
    const expectedSecret = env.PROXY_SECRET;
    if (!expectedSecret) {
      return new Response(
        JSON.stringify({
          error: {
            type: "proxy_misconfigured",
            message: "PROXY_SECRET is not set in Worker environment",
          },
        }),
        { status: 500, headers: { "content-type": "application/json" } },
      );
    }
    if (request.headers.get("x-proxy-secret") !== expectedSecret) {
      return new Response(
        JSON.stringify({
          error: {
            type: "unauthorized",
            message: "missing or invalid x-proxy-secret",
          },
        }),
        { status: 401, headers: { "content-type": "application/json" } },
      );
    }

    const upstreamUrl = `https://${UPSTREAM_HOST}${url.pathname}${url.search}`;

    const upstreamHeaders = new Headers();
    for (const [key, value] of request.headers.entries()) {
      if (!STRIP_HEADERS.has(key.toLowerCase())) {
        upstreamHeaders.set(key, value);
      }
    }

    let upstreamResponse;
    try {
      upstreamResponse = await fetch(upstreamUrl, {
        method: request.method,
        headers: upstreamHeaders,
        body: request.body,
      });
    } catch (err) {
      const detail = err && err.message ? err.message : String(err);
      return new Response(
        JSON.stringify({
          error: {
            type: "proxy_upstream_error",
            message: `worker failed to reach ${UPSTREAM_HOST}: ${detail}`,
          },
        }),
        { status: 502, headers: { "content-type": "application/json" } },
      );
    }

    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      statusText: upstreamResponse.statusText,
      headers: new Headers(upstreamResponse.headers),
    });
  },
};

# Approach B — Higgsfield Marketing Studio (Fallback)

> This is our **fallback**. We are not building it now. It is kept here so that if Approach A
> underdelivers, we can pick it up without re-thinking it from scratch.

## Summary

Instead of building our own image stack, use Higgsfield's Marketing Studio — it already produces
ad-quality, product-grounded creatives. We reach it through a small **sidecar** service so the
main engine only ever makes clean HTTP calls.

## Why it's the fallback, not the primary

- It is a wrapper on top of a wrapper, which is harder to control and maintain.
- It depends on Higgsfield's availability and access model.
- Higgsfield is reached over MCP (with OAuth), which adds integration overhead.

We keep it because Higgsfield's rendering is mature — a strong safety net if our own engine
isn't good enough fast enough.

## How it would work

```
brief → build product (Firecrawl pulls images from the URL) → create Higgsfield product (logo-locked)
      → generate image (Higgsfield) → check quality → deliver
```

## The sidecar (the key piece)

One small service is the **only** thing that talks to Higgsfield. The engine calls it over plain HTTP.

- Talks to: `https://mcp.higgsfield.ai/mcp` (OAuth). Tool chain: import image → create product → generate image → poll → URL.
- Auth: reuse the existing OAuth helper (`poll_higgsfield_oauth.py`) — one-time approval, then refreshes on its own.
- Endpoints the engine sees:
  ```
  POST /product   { url, logo_url? }            → { product_id }
  POST /image     { product_id, prompt, ratio } → { image_url }
  GET  /health
  ```

## Product source

Higgsfield products need images. The campaign step only captures the URL, so we use **Firecrawl**
(existing credits) to pull images from the site and feed them into the product.

## If we ever switch to this

1. Ask Higgsfield for a direct REST API / service token (we are a paying customer). If granted,
   the sidecar's internals get simpler.
2. Build the sidecar (the three endpoints above).
3. Point the engine's image step at the sidecar instead of `gpt-image-2`.

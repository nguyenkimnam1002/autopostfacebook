# affiliate_hot_tool task

## User asks (VN)
- Why is FB API connection convoluted; fix posting when 2+ products checked
- Make flow standard & post to FB
- Analyze step must fetch product images/videos and show in checkbox list (incl video)

## Root causes found
1. Posting fail = EXPIRED short-lived Page token in .env (expired 18-Jun 09:00 PDT). Not "2 products".
2. OAuth never completed -> no data/facebook_auth.json (long-lived). facebook_oauth_error.json = DNS err. Falls back to expiring .env token.
3. No media: Shopee affiliate CSV has no image/video cols; server-side Shopee scrape bot-blocked. Need Shopee API via logged-in Chrome (fetch_json_in_shopee_chrome) or cookie.

## Key files
- web_app.py: handlers + _page() HTML/JS (single file UI). _handle_analyze (bulk_csv), _handle_facebook_queue, _ranked_to_dict, _product_from_dict
- facebook_graph.py: publish_products_to_page, _publish_one (video/photo/feed)
- facebook_auth.py: OAuth, load_page_auth, SCOPES, exchange long-lived
- discovery.py: _product_from_shopee_item, _image_url, _video_url, search_items API; shopee_session.fetch_json_in_shopee_chrome (CDP)
- Product model has image_url/image_urls/video_url/video_urls

## STATUS: FULLY DONE + LIVE POST VERIFIED.
- User pasted User Token; exchanged -> PERMANENT page token (expires_at:0) saved data/facebook_auth.json. Page "Gia dung thong minh KN Tech" 9404 fans.
- Posted 2 products via /api/facebook-queue -> 2/2 OK, confirmed in feed, then deleted both test posts (success).
- Multi-product bug fixed & verified live.
## FEATURE: affiliate-link comment + media comments
- facebook_graph.py: _comment_affiliate_link posts "Mua hang ngay tai day 👇\\n{url}" as first comment on every post type (video/photo/feed). _publish_video_post now takes affiliate_url.
- BLOCKER: token needs pages_manage_engagement scope to comment. Current user token lacks it -> #200 error. Added scope to SCOPES + UI hint + friendly error. User must regenerate User Token WITH pages_manage_engagement and paste again. Not yet live-verified (test post deleted).
## FEATURE: self-service token validation (DONE)
- "Dung token lau dai" button FULLY DYNAMIC: reads body.token, no code change when user pastes new token. Button now DISABLED when textarea empty (input listener syncTokenBtn; re-disabled after clear on success).
- Progress bar code was always present (showPostProgress/updatePostProgress) but only runs via postSelectedViaGraph when graphReady. User saw no bar because stale server on :8001. RESTARTED server :8001 (Stop-Process on port then Start-Process python -m affiliate_tool.cli web). New code now live.
- Junk links/images in FB comments were from old running server; current _comment_media + _is_commentable_image (is_product_image) filter junk. Now live after restart.
- facebook_auth.py: added REQUIRED_SCOPES, SCOPE_LABELS (VN), inspect_token(token) -> {is_valid, scopes, granted_required, missing_required, expires_at} via debug_token w/ app token.
- web_app.py _handle_facebook_token_exchange: after exchange, calls inspect_token(page_token), builds VN message "Token hop le voi du N quyen: ... Ban duoc su dung token nay" or warns missing scopes. Returns granted_scopes/missing_scopes/all_required_granted.
- JS exchangeFacebookToken already shows payload.message. Tested live: current token reports all 4 required granted, expires_at 0.

## FEATURE: new token with engagement + junk image filter (DONE)
- User pasted NEW User Token WITH pages_manage_engagement. Exchanged -> PERMANENT page token (expires_at:0), scopes confirmed incl pages_manage_engagement,pages_manage_posts. Saved data/facebook_auth.json. Comment feature now unblocked (not yet live-posted this round).
- Junk-image fix: discovery.py added is_product_image(url) allowlist (Shopee CDN hosts + /file/ path; reject /product/, /null, /undefined, .svg, avatar, logo, non-shopee hosts). enrich_products_with_media now (a) cleans pre-existing junk images first, (b) uses ONLY get_pc API gallery images (filtered) as source of truth (no more merging CSV/page junk).
- facebook_graph.py _is_commentable_image now delegates to is_product_image.
- background.js scrapeProductMediaFromPage: removed broad whole-HTML regex + document.images + bg-image scraping (was grabbing ads/recommended/woman-in-dress). Now only og:image meta restricted to susercontent.com/file/. API path (scrapeProductDetailFromApi get_pc) unchanged = authoritative.
- Tested is_product_image: accepts down-vn.img.susercontent.com/file/*, cf.shopee.vn/file/*; rejects /product/.../null, example.com, avatar, .svg.

## FEATURE: progress bar + clean comments
- web_app.py: added progress bar (#postProgress/#postProgressBar), graph_configured in auth-status, postSelectedViaGraph posts one-by-one with % + 5s countdown between posts. graphReady flag.
- facebook_graph.py: _comment_media removed text-URL fallback (link rac); added _is_commentable_image filter (reject .svg, /null, /undefined, non-http). Comments only attach valid images different from title media.
## (old) STATUS: DONE (code). Blocker for live post = user must paste fresh User Token once.
Implemented & tested via server on :8011 (all endpoints 200). Changes:
- discovery.py: parse_shopee_ids, _shopee_get_json, fetch_product_media, enrich_products_with_media
- web_app.py: /api/enrich-media handler + _shopee_media_source; Shopee login/cookie buttons; FB long-lived token box+exchangeFacebookToken; enrichMediaViaBackend called after render; facebook-queue returns 200 partial results
- facebook_graph.py: 6s delay between posts; friendly expired-token msg -> points to long-lived box
- facebook_auth.py: exchange_user_token_to_page_auth (user token -> long-lived -> permanent page token -> data/facebook_auth.json)
- token-exchange endpoint /api/facebook-token-exchange

## Plan
- Media enrich backend via Shopee get_pc API (Chrome session/cookie), parse shop_id/item_id from URL, wire into analyze
- Posting: add delay between posts, partial results (no 500 whole batch), clear expired-token msg
- Token: add paste-token -> long-lived page token endpoint+UI to stop expiry
- Test analyze+media; FB posting blocked until user supplies fresh token

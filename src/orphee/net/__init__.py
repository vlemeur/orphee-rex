"""All network access lives here, behind a mockable interface.

http.HttpClient is the single HTTP gateway: identified User-Agent, politeness
delay between requests, tenacity retries on 429/5xx (honouring Retry-After,
failing fast above a cap), and a disk cache keyed by the sha256 of the
prepared URL so a re-run never hits the network twice. robots parses
robots.txt (Crawl-delay, Sitemap lines, Disallow of the '*' group).
Tests monkeypatch ``HttpClient.session.get`` — no network in tests.
"""

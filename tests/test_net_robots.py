"""Tests for orphee.net.robots — offline, synthetic robots.txt."""

from orphee.net.robots import parse_robots

ROBOTS = """
User-agent: *
Disallow: /login
Disallow: /recherche?
Crawl-delay: 10
Sitemap: https://reglementation-controle.asnr.fr/sitemap.xml

User-agent: BadBot
Crawl-delay: 60
Disallow: /
""".strip()


def test_parse_star_group() -> None:
    policy = parse_robots(ROBOTS)
    assert policy.crawl_delay_s == 10.0  # the '*' group, not BadBot's 60
    assert policy.sitemaps == ["https://reglementation-controle.asnr.fr/sitemap.xml"]
    assert policy.disallow == ["/login", "/recherche?"]


def test_is_allowed() -> None:
    policy = parse_robots(ROBOTS)
    assert policy.is_allowed("https://reglementation-controle.asnr.fr/controle/x")
    assert not policy.is_allowed("https://reglementation-controle.asnr.fr/login")
    assert not policy.is_allowed(
        "https://reglementation-controle.asnr.fr/recherche?q=x"
    )
    # "/recherche" without a query string is not covered by the "/recherche?" rule
    assert policy.is_allowed("https://reglementation-controle.asnr.fr/recherche")

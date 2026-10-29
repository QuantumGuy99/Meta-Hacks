"""Daily session quota and client IP resolution."""

from datetime import date

from starlette.requests import Request

from crucible.quota import DailyQuota, client_ip


def _request(forwarded: str | None = None, host: str = "10.0.0.1") -> Request:
    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    return Request({"type": "http", "headers": headers, "client": (host, 1234)})


def test_quota_refuses_after_the_daily_limit():
    quota = DailyQuota(2, today=lambda: date(2026, 10, 28))
    assert [quota.take("a"), quota.take("a"), quota.take("a")] == [True, True, False]
    assert quota.take("b")  # other clients are counted separately


def test_quota_resets_on_a_new_day():
    day = [date(2026, 10, 28)]
    quota = DailyQuota(1, today=lambda: day[0])
    assert quota.take("a") and not quota.take("a")
    day[0] = date(2026, 10, 29)
    assert quota.take("a")


def test_give_back_frees_a_slot_and_never_goes_negative():
    quota = DailyQuota(1, today=lambda: date(2026, 10, 28))
    quota.give_back("a")
    assert quota.take("a") and not quota.take("a")
    quota.give_back("a")
    assert quota.take("a")


def test_client_ip_uses_the_proxy_added_hop_not_a_forged_one():
    assert client_ip(_request("6.6.6.6, 203.0.113.9"), behind_proxy=True) == "203.0.113.9"


def test_client_ip_ignores_forwarded_for_without_a_proxy():
    assert client_ip(_request("203.0.113.9"), behind_proxy=False) == "10.0.0.1"
    assert client_ip(_request(None), behind_proxy=True) == "10.0.0.1"

"""Tests for mention policy utilities."""

from issuelab.mention_policy import check_rate_limit, filter_mentions, rank_mentions_by_frequency


def test_rank_mentions_by_frequency_orders_by_count_then_first_seen():
    text = "@a @b @a @c @b @a @d"
    ranked = rank_mentions_by_frequency(text)
    assert ranked == ["a", "b", "c", "d"]


def test_rank_mentions_by_frequency_keeps_first_casing():
    text = "@Alice says hi, then @alice again and @Bob"
    ranked = rank_mentions_by_frequency(text)
    # Should keep the first observed casing for each name
    assert ranked[0] == "Alice"
    assert ranked[1] == "Bob"


def test_filter_mentions_works_without_rate_limit_field(monkeypatch):
    # Keep this independent of local agents/ directory.
    monkeypatch.setattr("issuelab.mention_policy.load_registry", lambda *_a, **_k: {"gqy20": {"owner": "gqy20"}})
    allowed, filtered = filter_mentions(["gqy20", "ghost"], policy={"blacklist": []})
    assert allowed == ["gqy20"]
    assert filtered == ["ghost"]


def test_check_rate_limit_enforces_issue_and_hour_caps(monkeypatch):
    from issuelab import mention_policy as mp

    mp._RATE_LIMIT_STATE.clear()
    policy = {"enabled": True, "max_per_issue": 2, "max_per_hour": 2}

    assert check_rate_limit("gqy20", issue_number=1, rate_limit_policy=policy) is True
    assert check_rate_limit("gqy20", issue_number=1, rate_limit_policy=policy) is True
    # third mention on same issue should be blocked
    assert check_rate_limit("gqy20", issue_number=1, rate_limit_policy=policy) is False

"""Tests for mention policy utilities."""

from issuelab.mention_policy import rank_mentions_by_frequency


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

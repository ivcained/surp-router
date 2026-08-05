"""Tests for advisory voting on the cache flywheel proposal."""

import proposal_votes as pv


def setup_function():
    pv.reset_for_tests()


def test_valid_vote_is_counted():
    result = pv.cast_vote("voter-a", "hybrid", "ship it carefully")
    assert result["ok"] is True
    totals = pv.results()
    assert totals["total_votes"] == 1
    assert totals["options"]["hybrid"]["votes"] == 1


def test_voter_can_change_vote_without_increasing_total():
    pv.cast_vote("voter-a", "hybrid", "")
    pv.cast_vote("voter-a", "revnet", "changed mind")
    totals = pv.results()
    assert totals["total_votes"] == 1
    assert totals["options"]["hybrid"]["votes"] == 0
    assert totals["options"]["revnet"]["votes"] == 1


def test_invalid_option_is_rejected():
    result = pv.cast_vote("voter-a", "moon-token", "")
    assert result["ok"] is False
    assert pv.results()["total_votes"] == 0


def test_empty_voter_is_rejected():
    assert pv.cast_vote("", "hybrid", "")["ok"] is False


def test_comment_is_trimmed_and_limited():
    pv.cast_vote("voter-a", "juicebox", " x " * 500)
    comments = pv.recent_comments()
    assert len(comments) == 1
    assert len(comments[0]["comment"]) <= 280


def test_results_include_percentages_and_labels():
    pv.cast_vote("a", "hybrid", "")
    pv.cast_vote("b", "hybrid", "")
    pv.cast_vote("c", "offchain", "")
    totals = pv.results()
    assert totals["options"]["hybrid"]["pct"] == 66.67
    assert totals["options"]["offchain"]["pct"] == 33.33
    assert "label" in totals["options"]["hybrid"]

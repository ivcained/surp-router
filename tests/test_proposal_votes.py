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


# ── multi-proposal support (SRP contract vote) ─────────────────────────────

def test_srp_proposal_isolated_from_flywheel():
    pv.cast_vote("voter-a", "hybrid", "")  # flywheel vote
    res = pv.cast_vote("voter-a", "deploy", "", proposal="srp-contract")
    assert res["ok"] is True
    assert res["label"].startswith("Deploy SRP")
    fly = pv.results()  # default flywheel
    srp = pv.results(proposal="srp-contract")
    assert fly["total_votes"] == 1
    assert srp["total_votes"] == 1
    assert "deploy" in srp["options"]
    assert "deploy" not in fly["options"]


def test_srp_same_voter_can_vote_both_proposals():
    pv.cast_vote("voter-a", "hybrid", "", proposal="flywheel")
    pv.cast_vote("voter-a", "deploy-testnet", "", proposal="srp-contract")
    assert pv.results()["total_votes"] == 1
    assert pv.results(proposal="srp-contract")["total_votes"] == 1
    assert pv.results(proposal="srp-contract")["options"]["deploy-testnet"]["votes"] == 1


def test_srp_voter_can_change_without_double_count():
    pv.cast_vote("voter-a", "deploy", "", proposal="srp-contract")
    pv.cast_vote("voter-a", "wait", "", proposal="srp-contract")
    srp = pv.results(proposal="srp-contract")
    assert srp["total_votes"] == 1
    assert srp["options"]["deploy"]["votes"] == 0
    assert srp["options"]["wait"]["votes"] == 1


def test_srp_invalid_option_rejected():
    res = pv.cast_vote("voter-a", "hybrid", "", proposal="srp-contract")
    assert res["ok"] is False  # 'hybrid' is not an SRP-contract option
    assert pv.results(proposal="srp-contract")["total_votes"] == 0


def test_srp_comments_separate():
    pv.cast_vote("voter-a", "deploy", "srp comment", proposal="srp-contract")
    pv.cast_vote("voter-a", "hybrid", "flywheel comment")
    assert pv.recent_comments(proposal="srp-contract")[0]["comment"] == "srp comment"
    assert pv.recent_comments()[0]["comment"] == "flywheel comment"

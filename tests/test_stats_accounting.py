import stats


def test_global_stats_separates_x402_and_api_key_and_uses_microcents(tmp_path):
    stats.DB_PATH = str(tmp_path / "stats.db")
    stats._conn = None
    stats.log_request("x", "m", "0x1", 10000, "0xtx", "x402")
    stats.log_request("x", "m", "key:abc", 20000, "", "api_key")
    out = stats.global_stats()
    assert out["total_usdc_cents"] == 3
    assert out["x402_settled_usdc_cents"] == 1
    assert out["api_key_accounting_usdc_cents"] == 2

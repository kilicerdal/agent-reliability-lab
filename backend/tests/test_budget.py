from concurrent.futures import ThreadPoolExecutor

import pytest
from lab.budget import Budget, BudgetExceeded


def test_unknown_usage_remains_reserved(tmp_path):
    b = Budget(tmp_path / "budget.db")
    b.reserve()
    assert b.summary()["accounted_usd"] == 0.25
    assert Budget(b.path).summary()["unsettled_requests"] == 1


def test_tokens_settle_conservatively(tmp_path):
    b = Budget(tmp_path / "budget.db")
    r = b.reserve()
    assert b.settle(r, 1000, 1000) == 0.012
    assert b.summary()["accounted_usd"] == 0.012


def test_atomic_cap_across_concurrent_writers(tmp_path):
    b = Budget(tmp_path / "budget.db")
    with b.db() as c:
        c.execute(
            "INSERT INTO charges VALUES(?,?,?,?)", ("prior", 54.5, "usage-estimate", 0)
        )

    def reserve(_):
        try:
            b.reserve()
            return True
        except BudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(reserve, range(6)))
    assert sum(results) == 2
    assert b.summary()["accounted_usd"] == 55


def test_oversized_usage_is_not_silently_forgiven(tmp_path):
    b = Budget(tmp_path / "budget.db")
    r = b.reserve()
    with pytest.raises(BudgetExceeded):
        b.settle(r, 1_000_000, 1_000_000)
    assert b.summary()["unsettled_requests"] == 1

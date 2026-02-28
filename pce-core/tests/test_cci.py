from pce.core.cci import CCIInput, CCIMetric


def test_cci_computation_normalized() -> None:
    metric = CCIMetric()
    score = metric.compute(CCIInput(0.8, 0.7, 0.1, 0.6))
    assert 0.0 <= score <= 1.0
    assert round(score, 3) == 0.77

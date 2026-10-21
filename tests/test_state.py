import pytest
from pydantic import ValidationError
from state import Evidence


def test_weight_is_product():
    e = Evidence(agent="a", finding="f", signal="risk", severity=0.5, confidence=0.5, source_reliability=0.4)
    assert e.weight == pytest.approx(0.1)


def test_out_of_range_rejected():
    with pytest.raises(ValidationError):
        Evidence(agent="a", finding="f", signal="risk", severity=1.5, confidence=0.5)


def test_bad_signal_rejected():
    with pytest.raises(ValidationError):
        Evidence(agent="a", finding="f", signal="maybe", severity=0.5, confidence=0.5)
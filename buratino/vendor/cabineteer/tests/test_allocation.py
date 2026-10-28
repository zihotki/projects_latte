import pytest

from cabineteer.allocation import Fixed, Fr, allocate_tracks


def test_weighted_tracks_keep_remainder():
    result = allocate_tracks(1001, (Fixed(300), Fr(1), Fr(2)), reserved=4)
    assert result.lengths == (300, 232, 464)
    assert result.slack == 1


def test_fixed_slack_and_invalid_inputs():
    assert allocate_tracks(1000, (300, 300), 10).slack == 390
    with pytest.raises(ValueError, match="exceed"):
        allocate_tracks(609, (300, 300), 10)
    with pytest.raises(ValueError, match="weight"):
        allocate_tracks(10, (Fr(0),))
    with pytest.raises(ValueError, match="zero"):
        allocate_tracks(1, (Fr(1), Fr(2)))


def test_exact_weighted_arithmetic_and_fractional_budget_rejection():
    assert allocate_tracks(50, (Fr(58), Fr(42))).lengths == (29, 21)
    assert allocate_tracks(50, (Fr(10**500), Fr(10**500))).lengths == (25, 25)
    with pytest.raises(ValueError, match="integral"):
        allocate_tracks(50.5, (Fr(1),))

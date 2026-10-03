from pipeline.model import risk


def test_levels():
    assert risk.level_of(0) == 0 and risk.level_of(45) == 2 and risk.level_of(95) == 4


def test_local_scores_use_only_available_inputs():
    d = {"level": 1.0, "trend": 1.0, "station": {"t": "station", "en": "X", "th": "เอ็กซ์", "prov": "Y", "pct": 110, "trend": "rising_fast"}}
    s = risk.local_scores(d)
    assert len(s) == risk.DAYS and s[0][0] == 1.0
    assert s[0][1][0][1]["pct"] == 110


def test_no_inputs_gives_none():
    assert risk.local_scores({})[0][0] is None


def test_terrain_factor_bounds():
    assert risk.terrain_factor(0) > risk.terrain_factor(500)
    assert risk.terrain_factor(None) == 1.0

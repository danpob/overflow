from pipeline.transform import crossings


def test_km_known_distance():
    # Bangkok -> Ayutthaya is roughly 70 km
    assert 60 < crossings._km(13.75, 100.5, 14.35, 100.57) < 75


def test_direction_along_river():
    down = {1: 2, 2: 3, 3: 0, 9: 3}          # 1 -> 2 -> 3 (outlet); 9 is a tributary joining at 3
    assert crossings._direction(down, 1, 3) == "upstream"      # station above the crossing
    assert crossings._direction(down, 3, 1) == "downstream"    # station below the crossing
    assert crossings._direction(down, 9, 1) == "nearby"        # different branch
    assert crossings._direction(down, 2, 2) == "here"


def test_build_without_static_file_is_empty(monkeypatch):
    monkeypatch.setattr(crossings, "load_crossings", lambda: [])
    assert crossings.build(None, None, {}) == []

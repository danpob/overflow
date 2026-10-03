import json
from pathlib import Path

import pytest

from pipeline.publish.gold import trend_of
from pipeline.sources.thaiwater import SourceError, parse_waterlevel

FIX = Path(__file__).parent / "fixtures" / "waterlevel_load.json"


def test_parse_fixture():
    st = parse_waterlevel(json.loads(FIX.read_text()))
    assert len(st) > 700
    assert all(5 < s.lat < 21 for s in st)


def test_bad_shape_raises():
    with pytest.raises(SourceError):
        parse_waterlevel({"nope": 1})


def test_trend():
    st = parse_waterlevel(json.loads(FIX.read_text()))[0]
    st.level_msl, st.level_prev_msl = 3.0, 2.7
    assert trend_of(st) == "rising_fast"
    st.level_prev_msl = 3.0
    assert trend_of(st) == "stable"

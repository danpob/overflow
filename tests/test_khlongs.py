import geopandas as gpd
from shapely.geometry import Point

from pipeline.transform import khlongs

STATIC = {"1": {"name": "คลองA", "lines": [[[100.0, 14.0], [100.01, 14.01]]]},
          "2": {"name": "คลองB", "lines": [[[101.0, 15.0], [101.01, 15.01]]]}}


def frame(rows):
    return gpd.GeoDataFrame(rows, geometry=[Point(0, 0)] * len(rows), crs="EPSG:4326")


def test_only_stations_at_or_above_90_percent_are_drawn():
    sn = frame([{"id": 1, "pct_capacity": 95.0}, {"id": 2, "pct_capacity": 60.0}])
    out = khlongs.build(sn, STATIC)
    assert [f["properties"]["sid"] for f in out["features"]] == [1]
    assert out["features"][0]["geometry"]["type"] == "MultiLineString"


def test_stations_without_a_matched_waterway_or_bad_readings_are_skipped():
    sn = frame([{"id": 3, "pct_capacity": 120.0}, {"id": 1, "pct_capacity": 900.0}, {"id": 2, "pct_capacity": None}])
    assert khlongs.build(sn, STATIC)["features"] == []


def test_empty_static_gives_empty_collection():
    assert khlongs.build(frame([{"id": 1, "pct_capacity": 100.0}]), {})["features"] == []

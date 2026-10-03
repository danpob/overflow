# Overflow — Thailand Flood Tracker

Live site: https://danpob.github.io/overflow/ · refreshed about every 3 hours by GitHub Actions.

Map of where flood water in Thailand is heading and which river sub-basins are most at risk over the next 3 days. Public data only; static site, no server or database. **Not an official warning.** See `thailand-flood-tracker-PRD.md` and `progress.md`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python static_layers/build_static.py   # one-time: needs raw HydroSHEDS files in static_layers/raw (see docs/sources.md)
.venv/bin/python -m pipeline.run                 # fetch data -> web/data
python3 -m http.server 8765 --directory web      # open http://localhost:8765
.venv/bin/python -m pytest -q
```

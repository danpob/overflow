# Data sources (verified 3 Oct 2026)
| Source | Endpoint | Access | Notes |
|---|---|---|---|
| ThaiWater (HII) | `https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load` | keyless, undocumented | ~808 stations incl. bank levels. Occasionally returns 200 with a backend error body -> adapter retries. `dam_daily` returned 404: dam endpoint still TBD. **Confirm terms of use.** |
| Open-Meteo forecast | `api.open-meteo.com/v1/forecast` | keyless, free non-commercial | daily precipitation, per basin centroid |
| Open-Meteo flood (GloFAS) | `flood-api.open-meteo.com/v1/flood` | keyless, free non-commercial | 5 km cells; cells missing the river are discarded by comparing with HydroRIVERS mean flow |
| HydroRIVERS v10 (Asia) | `data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_as_shp.zip` | open download | unzip to `static_layers/raw/rivers/` |
| HydroBASINS lev07 (Asia) | `data.hydrosheds.org/file/HydroBASINS/standard/hybas_as_lev07_v1c.zip` | open download | unzip to `static_layers/raw/basins7/` |
| geoBoundaries THA ADM1 | geoBoundaries gbOpen (simplified) | open | save as `static_layers/raw/provinces.geojson` |

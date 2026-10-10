"""Reduce the raw satellite and station files to the small dataset kept in the
paper repository, from which the case-study figure and numbers are computed.

The raw inputs are too large to version (the NDMI tiles are about 81 GB), so
this script records exactly how the versioned files were derived from them:

  data/ndmi_csolnok_field.npz      NDMI of every scene, cropped to the field,
                                   NaN outside it and outside [-1, 1]
  data/station_csolnok_daily.csv   daily means of the Csolnok station
  data/field_csolnok.geojson       the field boundary (EPSG:23700)
  data/ndmi_field_meta.json        field area, pixel size, station distances

Needs rasterio and geopandas (tf210 environment), and the raw files:

    C:/Users/User/anaconda3/envs/tf210/python.exe tools/paper/build_ndmi_dataset.py
"""
import os, re, json, pathlib, datetime as dt
import numpy as np
import pandas as pd
import geopandas as gpd
import rasterio
from rasterio.mask import mask as rio_mask
from shapely.geometry import Point
import paper_data as pd_

BASE = pathlib.Path(r"C:/Users/User/Documents/Projects")
NDMI_DIR = pathlib.Path(os.environ.get("NDMI_DIR", BASE / "LandCoverNDMI/NDMI_CSOLNOK"))
SHAPE = pathlib.Path(os.environ.get("FIELD_SHP", BASE / "LandCoverNDMI/ThematicMaps/Hatar_73_tomb.shp"))
WEATHER = pathlib.Path(os.environ.get("WEATHER_CSV", BASE / "SoilSensor/pivoted_all_data.csv"))
STATION = "Csolnok"
CRS = "EPSG:23700"          # Hungarian EOV; the shapefile carries no .prj
H, W = 128, 112             # every crop is placed top-left on this grid

g = gpd.read_file(SHAPE)
if g.crs is None:
    g = g.set_crs(CRS)
poly = g.geometry.union_all() if hasattr(g.geometry, "union_all") else g.geometry.unary_union

names, dates, sats, levels, stack, pix = [], [], [], [], [], None
for f in sorted(NDMI_DIR.glob("*.tif")):
    m = re.match(r"(S2[AB])_MSI(L\w\w)_(\d{8})T", f.name)
    if not m:
        continue
    with rasterio.open(f) as src:
        if pix is None:
            pix = (abs(src.transform.a), abs(src.transform.e))
        a, _ = rio_mask(src, [poly], crop=True, all_touched=False, nodata=np.nan, filled=True)
    a = a[0].astype("float32")
    a[(a < -1) | (a > 1)] = np.nan
    full = np.full((H, W), np.nan, dtype="float32")
    full[:a.shape[0], :a.shape[1]] = a[:H, :W]
    stack.append(full)
    names.append(f.name)
    sats.append(m.group(1))
    levels.append(m.group(2))
    dates.append(dt.datetime.strptime(m.group(3), "%Y%m%d").date().isoformat())

pd_.DATA.mkdir(exist_ok=True)
np.savez_compressed(pd_.NDMI_STACK, ndmi=np.stack(stack), date=np.array(dates), satellite=np.array(sats),
                    level=np.array(levels), source_file=np.array(names))

w = pd.read_csv(WEATHER)
s = w[w.station_name == STATION].copy()
s["date"] = pd.to_datetime(dict(year=s.year, month=s.month, day=s.day)).dt.date
daily = (s.groupby("date")[["soil_moisture", "soil_temperature", "air_temperature", "relative_humidity"]]
         .mean().reset_index())
daily.to_csv(pd_.STATION_DAILY, index=False, lineterminator="\n")

# EOV convention: X is the northing and Y the easting
pt = Point(float(s.station_eovy.iloc[0]), float(s.station_eovx.iloc[0]))
meta = {
    "field_ha": poly.area / 1e4,
    "pixel_m": pix[0],
    "pixel_m2": pix[0] * pix[1],
    "stations_in_network_file": int(w.station_name.nunique()),
    "station": STATION,
    "station_easting_eov": pt.x,
    "station_northing_eov": pt.y,
    "station_to_boundary_m": poly.distance(pt),
    "station_to_centroid_m": poly.centroid.distance(pt),
    "station_inside_field": bool(poly.contains(pt)),
    "crs": CRS,
    "grid": [H, W],
}
pd_.FIELD_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
gpd.GeoDataFrame(geometry=[poly], crs=CRS).to_file(pd_.DATA / "field_csolnok.geojson", driver="GeoJSON")

print(f"{len(stack)} scenes -> {pd_.NDMI_STACK.name} ({pd_.NDMI_STACK.stat().st_size/1e6:.2f} MB)")
print(f"{len(daily)} station days -> {pd_.STATION_DAILY.name}")
print(f"field {meta['field_ha']:.2f} ha, station {meta['station_to_boundary_m']:.0f} m from the boundary")

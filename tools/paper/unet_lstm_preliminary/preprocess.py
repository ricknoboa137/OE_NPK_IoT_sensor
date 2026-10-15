"""Preprocessing of the preliminary UNet-LSTM run, as it was coded in the notebooks.

Two preprocessing paths existed, and both are reproduced unchanged:

  training stack   Weather_Stations_DataAnalysis.ipynb, cell 25: every scene is
                   masked to the field (all_touched=True, outside the field set to
                   1), then padded or cropped about its center to 128 x 112.
  display scenes   MoistureLSTM.ipynb, cell 14: the same masking without an
                   explicit no-data value, NDMI rescaled to (x + 1) / 2, padded
                   with -1.2; cell 15 plotted the first three of these (the first
                   is the paper's figure).

The files are taken in the order os.listdir returns them on Windows, which is
alphabetical; sorted() is used here so the order does not depend on the system.

Writes, in data/unet_preliminary/ of the paper repository:
  ndmi_stack_preliminary.npz        the 166 x 128 x 112 training stack and file order
  preprocessed_scenes_display.npz   the three display scenes with their extents

Needs rasterio and geopandas, and the raw NDMI tiles (tf210 environment):

    C:/Users/User/anaconda3/envs/tf210/python.exe preprocess.py
"""
import os, re, sys, pathlib
import numpy as np
import rasterio
import geopandas as gpd
from rasterio.mask import mask
from rasterio.transform import Affine

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paper_data

IMAGE_FOLDER = os.environ.get("NDMI_DIR", "C:/Users/User/Documents/Projects/LandCoverNDMI/NDMI_CSOLNOK")
SHAPEFILE = os.environ.get("FIELD_SHP", "C:/Users/User/Documents/Projects/LandCoverNDMI/ThematicMaps/Hatar_73_tomb.shp")
OUT = paper_data.DATA / "unet_preliminary"
TARGET_HEIGHT, TARGET_WIDTH = 128, 112


def standardize_raster_shape(data, transform, target_height, target_width, nodata_value):
    """Pad about the center with nodata_value, then crop about the center (both notebooks)."""
    num_bands, current_height, current_width = data.shape
    new_data, new_transform = data, transform
    if current_height < target_height or current_width < target_width:
        pad_height = target_height - current_height
        pad_width = target_width - current_width
        pad_top = pad_height // 2
        pad_bottom = pad_height - pad_top
        pad_left = pad_width // 2
        pad_right = pad_width - pad_left
        new_data = np.pad(data, ((0, 0), (pad_top, pad_bottom), (pad_left, pad_right)),
                          mode="constant", constant_values=nodata_value)
        new_transform = Affine(transform.a, transform.b, transform.c + pad_left * transform.a,
                               transform.d, transform.e, transform.f + pad_top * transform.e)
    h, w = new_data.shape[1], new_data.shape[2]
    if h > target_height or w > target_width:
        r0 = (h - target_height) // 2
        c0 = (w - target_width) // 2
        new_data = new_data[:, r0:r0 + target_height, c0:c0 + target_width]
        new_transform = Affine(new_transform.a, new_transform.b, new_transform.c + c0 * new_transform.a,
                               new_transform.d, new_transform.e, new_transform.f + r0 * new_transform.e)
    return new_data, new_transform


def boundary(src):
    bnd = gpd.read_file(SHAPEFILE)
    bnd.crs = "epsg:23700"
    if bnd.crs != src.crs:
        bnd = bnd.to_crs(src.crs)
    return bnd


def training_scene(path):
    """Weather_Stations_DataAnalysis.ipynb, cell 25 (NODATA_VALUE = 1)."""
    with rasterio.open(path) as src:
        bnd = boundary(src)
        data, tr = mask(src, [bnd.geometry.iloc[0]], crop=True, all_touched=True, nodata=1, filled=True)
        return standardize_raster_shape(data, tr, TARGET_HEIGHT, TARGET_WIDTH, 1)


def display_scene(path):
    """MoistureLSTM.ipynb, cell 14 (no explicit nodata in mask; padding with -1.2)."""
    with rasterio.open(path) as src:
        bnd = boundary(src)
        b = bnd.bounds
        extent = [b["minx"][0], b["maxx"][0], b["miny"][0], b["maxy"][0]]
        data, tr = mask(src, [bnd.geometry.iloc[0]], crop=True, all_touched=True, filled=True)
        # In the saved notebook this line is commented out, but it was active when cell 15
        # drew the figure: only with it does the figure come out pixel-identical.
        data = (data + 1) / 2
        data, tr = standardize_raster_shape(data, tr, TARGET_HEIGHT, TARGET_WIDTH, -1.2)
        return data, extent


files = [f for f in sorted(os.listdir(IMAGE_FOLDER)) if f.endswith(".tif")]
OUT.mkdir(parents=True, exist_ok=True)

stack = []
for f in files:
    data, _ = training_scene(os.path.join(IMAGE_FOLDER, f))
    stack.append(data[0])
np.savez_compressed(OUT / "ndmi_stack_preliminary.npz", ndmi=np.stack(stack).astype("float32"),
                    source_file=np.array(files))
print(f"training stack: {len(stack)} scenes of {stack[0].shape} -> ndmi_stack_preliminary.npz")

shown, extents, dates = [], [], []
for f in files[:3]:
    data, extent = display_scene(os.path.join(IMAGE_FOLDER, f))
    shown.append(data[0])
    extents.append(extent)
    ts = f.split("_")[2]
    dates.append(f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}")
np.savez_compressed(OUT / "preprocessed_scenes_display.npz", ndmi=np.stack(shown), extent=np.array(extents),
                    date=np.array(dates), source_file=np.array(files[:3]))
print(f"display scenes: {dates} -> preprocessed_scenes_display.npz")

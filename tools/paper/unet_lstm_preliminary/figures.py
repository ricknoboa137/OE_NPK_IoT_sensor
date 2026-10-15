"""Redraw two figures of the preliminary run from the archived data, with the
plotting code of the notebooks, and compare them with the recorded originals.

  preprocessed scene   MoistureLSTM.ipynb, cell 15, first scene
  training history     Weather_Stations_DataAnalysis.ipynb, cell 32, drawn from
                       the 20-epoch log archived in training_log.csv

The notebooks displayed figures inline, which saves them at 100 dpi with a tight
bounding box; the same is done here. Results go to data/unet_preliminary/regenerated/.

    C:/Users/User/anaconda3/envs/tf210/python.exe figures.py
"""
import csv, sys, pathlib
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from rasterio import plot as rasterplot
from PIL import Image

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paper_data

D = paper_data.DATA / "unet_preliminary"
OUT = D / "regenerated"
OUT.mkdir(exist_ok=True)
INLINE = dict(dpi=100, bbox_inches="tight", facecolor="white")


def preprocessed_scene():
    z = np.load(D / "preprocessed_scenes_display.npz")
    ndmi, extent, date = z["ndmi"][0], list(z["extent"][0]), str(z["date"][0])
    fig, ax1 = plt.subplots(1, 1, figsize=(5, 5))
    plt.subplot(1, 1, 1)
    rasterplot.show(ndmi, extent=extent, ax=ax1, contour=False, cmap="viridis")
    plt.title(f"NDMI for {date}")
    path = OUT / "preprocessed_scene_1.png"
    fig.savefig(path, **INLINE)
    plt.close("all")
    return path


def training_history():
    with open(D / "training_log.csv", encoding="utf-8") as f:
        h = {k: [float(r[k]) for r in rows] for rows in [list(csv.DictReader(f))] for k in rows[0]}
    plt.figure(figsize=(18, 6))
    for k, (train, val, title, ylabel, label) in enumerate((
            ("loss", "val_loss", "Model Loss (MSE)", "Loss", "Loss"),
            ("masked_mae", "val_masked_mae", "Model Mean Absolute Error", "MAE", "MAE"),
            ("masked_psnr", "val_masked_psnr", "Model PSNR", "PSNR", "PSNR")), 1):
        plt.subplot(1, 3, k)
        plt.plot(h[train], label=f"Train {label}")
        plt.plot(h[val], label=f"Validation {label}")
        plt.title(title)
        plt.xlabel("Epoch")
        plt.ylabel(ylabel)
        plt.legend()
        plt.grid(True)
    plt.tight_layout()
    path = OUT / "training_history.png"
    plt.savefig(path, **INLINE)
    plt.close("all")
    return path


def compare(new, original):
    a = np.asarray(Image.open(new).convert("RGB")).astype(int)
    b = np.asarray(Image.open(original).convert("RGB")).astype(int)
    if a.shape != b.shape:
        return f"size {a.shape[1]}x{a.shape[0]} against {b.shape[1]}x{b.shape[0]} of the original"
    d = np.abs(a - b)
    return (f"identical" if d.max() == 0 else
            f"{100 * (d.sum(axis=2) > 0).mean():.2f} % of pixels differ, largest difference {d.max()}")


if __name__ == "__main__":
    for make, original in ((preprocessed_scene, "original_preprocessed_scene_1.png"),
                           (training_history, "original_training_history.png")):
        path = make()
        print(f"{path.name:28} {compare(path, D / original)}")

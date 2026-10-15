"""Archive the recorded outputs of the preliminary UNet-LSTM run.

The run was made in two notebooks, which kept their outputs:
  Weather_Stations_DataAnalysis.ipynb (WREN repository, commit d890286)
      cell 32: the training log of 20 epochs and the training-history figure
      cell 33: five prediction samples
  MoistureLSTM.ipynb (LandCoverNDMI project folder)
      cell 15: three preprocessed scenes, the first of which is the paper's figure

This script copies those outputs, unchanged, into data/unet_preliminary/ of the
paper repository: the log as CSV and every figure as PNG. Run once.

    C:/Users/User/anaconda3/python.exe archive_notebook_outputs.py
"""
import base64, csv, json, re, subprocess, sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import paper_data

OUT = paper_data.DATA / "unet_preliminary"
OUT.mkdir(parents=True, exist_ok=True)

WREN = pathlib.Path(r"C:/Users/User/Documents/GitHub/WREN")
TRAIN_NB = json.loads(subprocess.run(
    ["git", "-C", str(WREN), "show", "d890286:Weather_Stations_DataAnalysis.ipynb"],
    capture_output=True, check=True).stdout.decode("utf-8"))
PREP_NB = json.load(open(r"C:/Users/User/Documents/Projects/LandCoverNDMI/MoistureLSTM.ipynb", encoding="utf-8"))


def images(cell):
    return [base64.b64decode(o["data"]["image/png"]) for o in cell.get("outputs", [])
            if "image/png" in o.get("data", {})]


def text(cell):
    return "".join("".join(o.get("text", [])) for o in cell.get("outputs", []))


# training log
log = text(TRAIN_NB["cells"][32])
pat = re.compile(r"Epoch (\d+)/\d+\n.*?loss: ([\d.e+-]+) - masked_mae: ([\d.e+-]+) - masked_psnr: ([\d.e+-]+) - "
                 r"masked_ssim: ([\d.e+-]+) - val_loss: ([\d.e+-]+) - val_masked_mae: ([\d.e+-]+) - "
                 r"val_masked_psnr: ([\d.e+-]+) - val_masked_ssim: ([\d.e+-]+)")
rows = pat.findall(log)
if len(rows) != 20:
    sys.exit(f"expected 20 epochs in the log, found {len(rows)}")
with open(OUT / "training_log.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["epoch", "loss", "masked_mae", "masked_psnr", "masked_ssim",
                "val_loss", "val_masked_mae", "val_masked_psnr", "val_masked_ssim"])
    w.writerows(rows)
(OUT / "training_console_output.txt").write_text(log, encoding="utf-8")

# figures, exactly as the notebooks stored them
hist = images(TRAIN_NB["cells"][32])
(OUT / "original_training_history.png").write_bytes(hist[0])
(OUT / "original_ssim_history.png").write_bytes(hist[1])
for k, png in enumerate(images(TRAIN_NB["cells"][33]), 1):
    (OUT / f"original_prediction_sample_{k}.png").write_bytes(png)
for k, png in enumerate(images(PREP_NB["cells"][15]), 1):
    (OUT / f"original_preprocessed_scene_{k}.png").write_bytes(png)

print(f"archived to {OUT}:")
for p in sorted(OUT.iterdir()):
    print(f"  {p.name}  ({p.stat().st_size} bytes)")

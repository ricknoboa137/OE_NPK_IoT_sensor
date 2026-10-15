# Preliminary UNet-LSTM run

The three model figures of the manuscript come from a preliminary run of the
UNet-LSTM NDMI forecaster, made in two notebooks:

| notebook | cells | produced |
| --- | --- | --- |
| `Weather_Stations_DataAnalysis.ipynb` (WREN repository, commit d890286) | 25, 31, 32, 33 | training stack, model, training log, training history, prediction samples |
| `MoistureLSTM.ipynb` (LandCoverNDMI project folder) | 14, 15 | preprocessed scenes |

This folder holds that code as scripts. The data and the recorded outputs are in
the paper repository, under `data/unet_preliminary/`.

| script | environment | what it does |
| --- | --- | --- |
| `archive_notebook_outputs.py` | base | copies the recorded outputs out of the notebooks: the 20-epoch log as CSV, and every figure unchanged (`original_*.png`). Run once. |
| `preprocess.py` | tf210 | reruns both preprocessing paths on the raw NDMI tiles and stores the training stack and the display scenes |
| `figures.py` | tf210 | redraws the preprocessed scene and the training history with the notebooks' plotting code, and compares them with the originals |
| `train.py` | tf210 | retrains the model with the notebook's code and the recorded settings |

## How exact the reproduction is

| figure in the manuscript | reproduced from | result |
| --- | --- | --- |
| `NDMI_preprocessed_sample.png` | `preprocessed_scenes_display.npz` with `figures.py` | pixel-identical |
| `UNetLSTM_training_history.png` (and its two-panel cut) | `training_log.csv` with `figures.py` | identical except along the curves (0.4 % of pixels), because the log keeps four decimals where the original plot used full precision |
| `UNetLSTM_prediction_sample.png` | archived as recorded | not regenerable: the run did not save its weights, and the sample was drawn at random without a seed. `train.py` reruns the procedure and gives samples of the same kind |

Every figure in the manuscript is byte-identical to the corresponding archived
notebook output (`original_*.png`).

## Notes on the recorded state

- The display scenes were drawn with the NDMI rescaled to (x + 1) / 2. That line
  is commented out in the saved notebook, but only with it does the figure come
  out identical, so it was active when the figure was made.
- The training cell shows `epochs = 10` and `batch_size = 5`, but it was edited
  after the run: the log records 20 epochs of 19 steps, which with
  `validation_split = 0.3` means `batch_size = 6`. `train.py` uses the recorded values.
- Files are processed in the order `os.listdir` returns on Windows (alphabetical);
  the scripts use `sorted()` so the order does not depend on the system.
- One epoch of `train.py` on CPU gives values close to the first epoch of the log
  (validation loss 0.032 against 0.025).

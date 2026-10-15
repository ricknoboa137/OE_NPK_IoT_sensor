"""Keep the loss and mean-absolute-error panels of the preliminary training history.

The source figure, Pic/UNetLSTM_training_history.png, has three panels side by
side (loss, mean absolute error, PSNR). The manuscript shows the first two; the
cut falls in the blank band between the second and the third panel.

    C:/Users/User/anaconda3/python.exe tools/paper/crop_unet_history.py
"""
from PIL import Image
import paper_data

SOURCE = paper_data.PAPER / "Pic" / "UNetLSTM_training_history.png"
TARGET = paper_data.PAPER / "Pic" / "UNetLSTM_training_history_loss_mae.png"
CUT_X = 1192      # inside the blank band at x = 1183-1198 of the 1790-pixel-wide source

im = Image.open(SOURCE)
im.crop((0, 0, CUT_X, im.height)).save(TARGET, optimize=True)
print(f"{TARGET.name}: {CUT_X} x {im.height} (from {im.width} x {im.height})")

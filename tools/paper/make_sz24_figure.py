"""Build the field figure, Pic/SZ24_field.png, from its two source images.

Sources, kept in the paper repository under data/figure_sz24/:
  slide1_3200x1800.png   slide 1 of Topography_.pptx exported at 3200 x 1800:
                         the topographic map with the field outlined in red and
                         the two elevation arrows
  p2o5_map.png           the interpolated P2O5 map of the twelve samples
                         (ppt/media/image4.png inside the same file)
  Topography_.pptx       the presentation both were taken from

The left panel is cropped from the slide, and its two elevation labels, written
with decimal commas in the slide, are redrawn with decimal points.

    C:/Users/User/anaconda3/python.exe tools/paper/make_sz24_figure.py
"""
from PIL import Image, ImageDraw, ImageFont
from matplotlib import font_manager
import paper_data as pd_

SLIDE_W_CM = 33.87                 # width of the 16:9 slide
CROP_CM = (1.4, 6.0, 14.6, 17.4)   # left, top, right, bottom of the map and its labels
LABELS = (((4.4, 16.1, 3.2, 1.0), "132.5 m"),    # (x, y, width, height) of each text box, in cm
          ((10.5, 16.1, 3.5, 1.0), "117.5 m"))
PANEL_HEIGHT = 1000
GAP = 40

slide = Image.open(pd_.SZ24_SOURCES / "slide1_3200x1800.png").convert("RGB")
px = slide.width / SLIDE_W_CM
left = slide.crop(tuple(int(v * px) for v in CROP_CM))

draw = ImageDraw.Draw(left)
font = ImageFont.truetype(font_manager.findfont("DejaVu Sans"), 60)   # ships with matplotlib
for (x, y, w, h), text in LABELS:
    box = (round((x - CROP_CM[0]) * px), round((y - CROP_CM[1]) * px),
           round((x - CROP_CM[0] + w) * px), round((y - CROP_CM[1] + h) * px))
    draw.rectangle(box, fill="white")
    tb = draw.textbbox((0, 0), text, font=font)
    draw.text((box[0] + ((box[2] - box[0]) - (tb[2] - tb[0])) // 2,
               box[1] + ((box[3] - box[1]) - (tb[3] - tb[1])) // 2 - tb[1]), text, fill="black", font=font)

right = Image.open(pd_.SZ24_SOURCES / "p2o5_map.png").convert("RGB")
lw = round(left.width * PANEL_HEIGHT / left.height)
rw = round(right.width * PANEL_HEIGHT / right.height)
out = Image.new("RGB", (lw + GAP + rw, PANEL_HEIGHT), "white")
out.paste(left.resize((lw, PANEL_HEIGHT), Image.LANCZOS), (0, 0))
out.paste(right.resize((rw, PANEL_HEIGHT), Image.LANCZOS), (lw + GAP, 0))
target = pd_.PAPER / "Pic" / "SZ24_field.png"
out.save(target, optimize=True)
print(f"figure written: {target}  {out.size}")

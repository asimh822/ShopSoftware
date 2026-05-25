"""
make_icon.py — generates icon.png and icon.ico for United Mobile EPOS
Run once:  python make_icon.py
Requires:  pip install Pillow
"""

from PIL import Image, ImageDraw
import os

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

BG_COLOR   = (31, 78, 121)    # #1F4E79  dark navy
FG_COLOR   = (255, 255, 255)  # white
ACC_COLOR  = (147, 197, 253)  # light blue accent  (#93c5fd)


def draw_icon(size: int) -> Image.Image:
    img  = Image.new("RGBA", (size, size), BG_COLOR + (255,))
    draw = ImageDraw.Draw(img)
    s    = size

    # ── phone body ───────────────────────────────────────────────────────────
    ph_w  = int(s * 0.38)
    ph_h  = int(s * 0.62)
    ph_x  = int((s - ph_w) / 2)
    ph_y  = int((s - ph_h) / 2)
    ph_r  = int(s * 0.06)

    draw.rounded_rectangle(
        [ph_x, ph_y, ph_x + ph_w, ph_y + ph_h],
        radius=ph_r,
        fill=FG_COLOR,
    )

    # inner screen (navy)
    scr_margin = int(s * 0.04)
    scr_top    = ph_y + int(ph_h * 0.14)
    scr_bot    = ph_y + int(ph_h * 0.82)
    draw.rounded_rectangle(
        [ph_x + scr_margin, scr_top,
         ph_x + ph_w - scr_margin, scr_bot],
        radius=int(ph_r * 0.5),
        fill=BG_COLOR,
    )

    # ── shop / store symbol inside screen ────────────────────────────────────
    cx      = ph_x + ph_w // 2
    cy      = scr_top + (scr_bot - scr_top) // 2
    shop_w  = int(ph_w * 0.55)
    shop_h  = int(ph_h * 0.38)
    sx      = cx - shop_w // 2
    sy      = cy - shop_h // 2
    roof_h  = int(shop_h * 0.36)
    body_h  = shop_h - roof_h
    lw      = max(1, int(s * 0.012))

    # roof triangle
    roof_pts = [
        (sx - int(shop_w * 0.08), sy + roof_h),
        (cx, sy),
        (sx + shop_w + int(shop_w * 0.08), sy + roof_h),
    ]
    draw.polygon(roof_pts, fill=ACC_COLOR)

    # body
    draw.rectangle(
        [sx + lw, sy + roof_h, sx + shop_w - lw, sy + shop_h],
        fill=FG_COLOR,
    )

    # door
    door_w = int(shop_w * 0.28)
    door_h = int(body_h * 0.50)
    door_x = cx - door_w // 2
    door_y = sy + roof_h + body_h - door_h
    draw.rounded_rectangle(
        [door_x, door_y, door_x + door_w, sy + shop_h],
        radius=int(door_w * 0.18),
        fill=BG_COLOR,
    )

    # sign bar
    sign_h = int(body_h * 0.28)
    draw.rectangle(
        [sx + lw, sy + roof_h, sx + shop_w - lw, sy + roof_h + sign_h],
        fill=ACC_COLOR,
    )

    # ── home button ──────────────────────────────────────────────────────────
    btn_r  = int(s * 0.027)
    btn_cx = ph_x + ph_w // 2
    btn_cy = ph_y + ph_h - int(ph_h * 0.07)
    draw.ellipse(
        [btn_cx - btn_r, btn_cy - btn_r,
         btn_cx + btn_r, btn_cy + btn_r],
        fill=BG_COLOR,
    )

    # ── ear speaker ──────────────────────────────────────────────────────────
    sp_w = int(ph_w * 0.28)
    sp_h = int(s * 0.018)
    sp_x = ph_x + (ph_w - sp_w) // 2
    sp_y = ph_y + int(ph_h * 0.065)
    draw.rounded_rectangle(
        [sp_x, sp_y, sp_x + sp_w, sp_y + sp_h],
        radius=sp_h // 2,
        fill=BG_COLOR,
    )

    return img


def main():
    master = draw_icon(256)

    png_path = os.path.join(OUTPUT_DIR, "icon.png")
    master.save(png_path, "PNG")
    print(f"Saved: {png_path}")

    # Build multi-size ICO — Pillow resamples from the 256×256 master
    ico_path   = os.path.join(OUTPUT_DIR, "icon.ico")
    ico_sizes  = [(16, 16), (32, 32), (48, 48), (256, 256)]
    master_rgb = master.convert("RGBA")
    master_rgb.save(ico_path, format="ICO", sizes=ico_sizes)
    print(f"Saved: {ico_path}  (sizes: 16, 32, 48, 256)")
    print("Icon generation complete.")


if __name__ == "__main__":
    main()

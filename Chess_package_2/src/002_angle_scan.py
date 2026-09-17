from pathlib import Path
import math

import numpy as np
from PIL import Image, ImageDraw


project_folder = (
    Path(__file__).resolve().parent.parent
    / "chess_package"
)
xyz_file = project_folder / "data" / "Processed" / "damaged_chess.xyz"
output_folder = project_folder / "figures" / "angle_scan"

output_folder.mkdir(parents=True, exist_ok=True)

points = np.loadtxt(xyz_file)

x = points[:, 0]
y = points[:, 1]
z = points[:, 2]

center_x = (x.min() + x.max()) / 2
center_y = (y.min() + y.max()) / 2

x = x - center_x
y = y - center_y

angles = list(range(0, 180, 5))

preview_width = 300
preview_height = 240
margin = 12

previews = []


def render_projection(angle):
    radians = math.radians(angle)

    # 围绕 Z 轴旋转后，将三维点压到 U-Z 平面
    u = x * math.cos(radians) + y * math.sin(radians)

    u_min = u.min()
    u_max = u.max()
    z_min = z.min()
    z_max = z.max()

    scale_x = (preview_width - margin * 2) / (u_max - u_min)
    scale_z = (preview_height - margin * 2 - 20) / (z_max - z_min)
    scale = min(scale_x, scale_z)

    image = Image.new(
        "RGB",
        (preview_width, preview_height),
        "white",
    )

    draw = ImageDraw.Draw(image)
    draw.text((8, 5), f"{angle} degrees", fill="black")

    offset_x = (
        preview_width / 2
        - ((u_min + u_max) / 2) * scale
    )

    offset_y = (
        preview_height - margin
        + z_min * scale
    )

    for point_u, point_z in zip(u, z):
        px = round(offset_x + point_u * scale)
        py = round(offset_y - point_z * scale)

        if 0 <= px < preview_width and 20 <= py < preview_height:
            draw.rectangle(
                (px - 1, py - 1, px + 1, py + 1),
                fill="black",
            )

    return image


for angle in angles:
    preview = render_projection(angle)
    previews.append(preview)

    preview.save(
        output_folder / f"angle_{angle:03d}.png"
    )

# 制作总览图
columns = 4
rows = math.ceil(len(previews) / columns)

contact_sheet = Image.new(
    "RGB",
    (
        columns * preview_width,
        rows * preview_height,
    ),
    "white",
)

for index, preview in enumerate(previews):
    column = index % columns
    row = index // columns

    contact_sheet.paste(
        preview,
        (
            column * preview_width,
            row * preview_height,
        ),
    )

contact_sheet.save(
    output_folder / "angle_contact_sheet.png"
)

print("角度扫描完成")
print("输出目录：", output_folder)
print("请打开 angle_contact_sheet.png")
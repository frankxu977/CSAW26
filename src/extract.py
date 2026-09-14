import csv
from pathlib import Path

import cv2
import numpy as np


BASE_WIDTH_MM = 30.0
CALIBRATION_Y = 600
MAX_Z = 23.95


PIECES = {
    "Pawn": {
        "center_x": 255,
        "top_y": 180,
        "bottom_y": 718,
        "height_mm": 45.0,
        "side": "left"
    },

    "Bishop": {
        "center_x": 555,
        "top_y": 110,
        "bottom_y": 718,
        "height_mm": 60.0,
        "side": "right_near"
    },

    "Queen": {
        "center_x": 855,
        "top_y": 20,
        "bottom_y": 718,
        "height_mm": 70.0,
        "side": "right"
    }
}


def get_half_width_pixels(edges, y, piece):
    center_x = piece["center_x"]
    side = piece["side"]

    if side == "left":
        start = max(0, center_x - 230)
        end = center_x - 5

        xs = np.where(
            edges[y, start:end] > 0
        )[0] + start

        if len(xs) == 0:
            return None, None

        edge_x = int(xs.min())

        half_width = center_x - edge_x

        return half_width, edge_x


    if side == "right":
        start = center_x + 5
        end = min(
            edges.shape[1],
            center_x + 231
        )

        xs = np.where(
            edges[y, start:end] > 0
        )[0] + start

        if len(xs) == 0:
            return None, None

        edge_x = int(xs.max())

        half_width = edge_x - center_x

        return half_width, edge_x


    if side == "right_near":
        start = center_x + 15
        end = min(
            edges.shape[1],
            center_x + 216
        )

        xs = np.where(
            edges[y, start:end] > 0
        )[0] + start

        if len(xs) == 0:
            return None, None

        if len(xs) > 12:
            return None, None

        edge_x = int(xs.min())

        half_width = edge_x - center_x

        return half_width, edge_x


    return None, None


def extract_profile(edges, piece):
    calibration_half_px, _ = get_half_width_pixels(
        edges,
        CALIBRATION_Y,
        piece
    )

    if calibration_half_px is None:
        raise RuntimeError(
            "Calibration failed"
        )

    half_base_mm = BASE_WIDTH_MM / 2.0

    mm_per_pixel_x = (
        half_base_mm /
        calibration_half_px
    )

    rows = []

    top_y = piece["top_y"]
    bottom_y = piece["bottom_y"]
    height_mm = piece["height_mm"]

    pixel_height = bottom_y - top_y

    for y in range(
        top_y,
        bottom_y + 1
    ):

        z_mm = (
            (bottom_y - y)
            * height_mm
            / pixel_height
        )

        if z_mm < 0:
            continue

        if z_mm > MAX_Z:
            continue

        half_width_px, edge_x = (
            get_half_width_pixels(
                edges,
                y,
                piece
            )
        )

        if half_width_px is None:
            continue

        half_width_mm = (
            half_width_px
            * mm_per_pixel_x
        )

        rows.append({
            "y_px": y,
            "z_mm": z_mm,
            "edge_x_px": edge_x,
            "half_width_px": half_width_px,
            "half_width_mm": half_width_mm
        })

    return rows


def save_csv(
    profiles,
    output_path
):
    fields = [
        "piece",
        "y_px",
        "z_mm",
        "edge_x_px",
        "half_width_px",
        "half_width_mm"
    ]

    with open(
        output_path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()

        for piece_name, rows in profiles.items():

            for row in rows:

                writer.writerow({
                    "piece": piece_name,
                    "y_px": row["y_px"],
                    "z_mm": f'{row["z_mm"]:.6f}',
                    "edge_x_px": row["edge_x_px"],
                    "half_width_px": row["half_width_px"],
                    "half_width_mm":
                        f'{row["half_width_mm"]:.6f}'
                })


def draw_check_image(
    image,
    profiles,
    output_path
):
    result = image.copy()

    for piece_name, rows in profiles.items():

        center_x = (
            PIECES[piece_name]["center_x"]
        )

        for row in rows:

            y = row["y_px"]
            edge_x = row["edge_x_px"]

            cv2.circle(
                result,
                (edge_x, y),
                1,
                (0, 0, 255),
                -1
            )

        cv2.line(
            result,
            (
                center_x,
                PIECES[piece_name]["top_y"]
            ),
            (
                center_x,
                PIECES[piece_name]["bottom_y"]
            ),
            (255, 0, 0),
            1
        )

    cv2.imwrite(
        str(output_path),
        result
    )


def main():
    folder = Path(__file__).resolve().parent

    image_path = (
        folder /
        "chess_pieces.png"
    )

    csv_path = (
        folder /
        "reference_profiles.csv"
    )

    check_path = (
        folder /
        "contour_check.png"
    )

    image = cv2.imread(
        str(image_path)
    )

    if image is None:
        print("Image not found:")
        print(image_path)
        return

    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )

    edges = cv2.Canny(
        gray,
        50,
        150
    )

    profiles = {}

    for name, piece in PIECES.items():

        profiles[name] = (
            extract_profile(
                edges,
                piece
            )
        )

        print(
            name,
            "points:",
            len(profiles[name])
        )

    save_csv(
        profiles,
        csv_path
    )

    draw_check_image(
        image,
        profiles,
        check_path
    )

    print()
    print("CSV:")
    print(csv_path)

    print()
    print("Check image:")
    print(check_path)


if __name__ == "__main__":
    main()
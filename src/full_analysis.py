import csv
import math
import re
from pathlib import Path

import cv2
import numpy as np
import matplotlib.pyplot as plt


BASE_IMAGE_W = 1112
BASE_IMAGE_H = 759

BODY_MIN_Z = 12.05

SENS_OFFSET_MIN = 0.0
SENS_OFFSET_MAX = 0.40
SENS_OFFSET_STEP = 0.025

SENS_ZSHIFT_MIN = -0.30
SENS_ZSHIFT_MAX = 0.30
SENS_ZSHIFT_STEP = 0.05


PIECE_INFO = {
    "Pawn": {
        "center_x": 255,
        "height_mm": 45.0,
        "cal_side": "left"
    },

    "Bishop": {
        "center_x": 555,
        "height_mm": 60.0,
        "cal_side": "right_near"
    },

    "Queen": {
        "center_x": 855,
        "height_mm": 70.0,
        "cal_side": "right"
    }
}


def read_metadata(gcode_path):

    text = Path(gcode_path).read_text(
        encoding="utf-8",
        errors="ignore"
    )

    def grab(
        pattern,
        default=None,
        cast=float
    ):
        match = re.search(
            pattern,
            text,
            flags=re.I
        )

        if not match:
            return default

        return cast(
            match.group(1)
        )

    return {
        "filament_used_mm":
            grab(
                r";\s*filament used\s*=\s*([0-9.]+)\s*mm"
            ),

        "external_width_mm":
            grab(
                r";\s*external perimeters extrusion width\s*=\s*([0-9.]+)\s*mm",
                0.5
            ),

        "layer_height_mm":
            grab(
                r";\s*layer_height\s*=\s*([0-9.]+)",
                0.1
            ),

        "filament_diameter_mm":
            grab(
                r";\s*filament_diameter\s*=\s*([0-9.]+)",
                1.0
            ),

        "top_solid_layers":
            grab(
                r";\s*top_solid_layers\s*=\s*([0-9]+)",
                10,
                int
            ),

        "perimeters":
            grab(
                r";\s*perimeters\s*=\s*([0-9]+)",
                1,
                int
            ),

        "fill_density_percent":
            grab(
                r";\s*fill_density\s*=\s*([0-9.]+)\s*%",
                0.0
            )
    }


def load_clean_deposition(path):

    rows = []

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            rows.append({
                "z":
                    float(row["z"]),

                "x1":
                    float(row["x1"]),

                "y1":
                    float(row["y1"]),

                "x2":
                    float(row["x2"]),

                "y2":
                    float(row["y2"]),

                "delta_e":
                    float(row["delta_e"]),

                "xy_distance":
                    float(row["xy_distance"])
            })

    return rows


def build_damaged_layers(
    rows,
    surface_offset
):

    layers = {}

    for row in rows:

        z = round(
            row["z"],
            5
        )

        if z not in layers:

            layers[z] = {
                "x": [],
                "y": [],
                "filament": 0.0,
                "path": 0.0
            }

        layers[z]["x"].extend([
            row["x1"],
            row["x2"]
        ])

        layers[z]["y"].extend([
            row["y1"],
            row["y2"]
        ])

        layers[z]["filament"] += (
            row["delta_e"]
        )

        layers[z]["path"] += (
            row["xy_distance"]
        )


    output = []

    for z in sorted(
        layers.keys()
    ):

        data = layers[z]

        xs = data["x"]
        ys = data["y"]

        xmin = min(xs)
        xmax = max(xs)

        ymin = min(ys)
        ymax = max(ys)

        half_x = (
            xmax - xmin
        ) / 2.0

        half_y = (
            ymax - ymin
        ) / 2.0

        half_centerline = (
            half_x +
            half_y
        ) / 2.0

        output.append({

            "z":
                z,

            "xmin":
                xmin,

            "xmax":
                xmax,

            "ymin":
                ymin,

            "ymax":
                ymax,

            "half_centerline":
                half_centerline,

            "half_surface":
                half_centerline
                + surface_offset,

            "filament":
                data["filament"],

            "path":
                data["path"],

            "square_path_expected":
                8.0
                * half_centerline
        })

    return output


def save_damaged_layers(
    rows,
    path
):

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(
                rows[0].keys()
            )
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def load_reference_profiles(path):

    pieces = {}

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            piece = row["piece"]

            if piece not in pieces:

                pieces[piece] = {
                    "z": [],
                    "half_width": []
                }

            pieces[piece][
                "z"
            ].append(
                float(
                    row["z_mm"]
                )
            )

            pieces[piece][
                "half_width"
            ].append(
                float(
                    row[
                        "half_width_mm"
                    ]
                )
            )


    for piece in pieces:

        z = np.array(
            pieces[piece]["z"],
            dtype=float
        )

        width = np.array(
            pieces[piece][
                "half_width"
            ],
            dtype=float
        )

        order = np.argsort(z)

        pieces[piece]["z"] = (
            z[order]
        )

        pieces[piece][
            "half_width"
        ] = width[order]

    return pieces


def compare_profile(
    damaged_layers,
    reference,
    offset,
    z_shift,
    min_z,
    max_z
):

    damaged_z = np.array([
        row["z"]
        for row
        in damaged_layers
    ])

    damaged_width = np.array([
        row[
            "half_centerline"
        ]
        for row
        in damaged_layers
    ])

    damaged_width = (
        damaged_width
        + offset
    )


    valid = (
        (damaged_z >= min_z)
        &
        (damaged_z <= max_z)
    )

    damaged_z = (
        damaged_z[valid]
    )

    damaged_width = (
        damaged_width[valid]
    )


    reference_z = (
        reference["z"]
        + z_shift
    )

    reference_width = (
        reference[
            "half_width"
        ]
    )


    min_common = max(
        damaged_z.min(),
        reference_z.min()
    )

    max_common = min(
        damaged_z.max(),
        reference_z.max()
    )


    valid = (
        (damaged_z >= min_common)
        &
        (damaged_z <= max_common)
    )

    damaged_z = (
        damaged_z[valid]
    )

    damaged_width = (
        damaged_width[valid]
    )


    if len(
        damaged_z
    ) < 5:

        return None


    reference_interp = (
        np.interp(
            damaged_z,
            reference_z,
            reference_width
        )
    )


    error = (
        damaged_width
        - reference_interp
    )


    return {

        "rmse":
            float(
                np.sqrt(
                    np.mean(
                        error ** 2
                    )
                )
            ),

        "mae":
            float(
                np.mean(
                    np.abs(
                        error
                    )
                )
            ),

        "max_error":
            float(
                np.max(
                    np.abs(
                        error
                    )
                )
            ),

        "points":
            len(error)
    }


def baseline_geometry(
    damaged_layers,
    references,
    offset,
    last_z
):

    results = []

    for piece, reference in (
        references.items()
    ):

        result = compare_profile(
            damaged_layers,
            reference,
            offset,
            0.0,
            0.45,
            last_z
        )

        results.append({

            "piece":
                piece,

            "rmse_mm":
                result["rmse"],

            "mae_mm":
                result["mae"],

            "max_error_mm":
                result[
                    "max_error"
                ],

            "points":
                result["points"]
        })


    return sorted(
        results,
        key=lambda x:
            x["rmse_mm"]
    )


def sensitivity_analysis(
    damaged_layers,
    references,
    last_z
):

    offsets = np.arange(
        SENS_OFFSET_MIN,
        SENS_OFFSET_MAX
        + 1e-12,
        SENS_OFFSET_STEP
    )

    shifts = np.arange(
        SENS_ZSHIFT_MIN,
        SENS_ZSHIFT_MAX
        + 1e-12,
        SENS_ZSHIFT_STEP
    )


    output = []

    winner_counts = {
        "full": {
            piece: 0
            for piece
            in references
        },

        "body": {
            piece: 0
            for piece
            in references
        }
    }


    ranges = [
        (
            "full",
            0.45
        ),

        (
            "body",
            BODY_MIN_Z
        )
    ]


    for range_name, min_z in ranges:

        for offset in offsets:

            for shift in shifts:

                metrics = {}

                for piece, reference in (
                    references.items()
                ):

                    result = (
                        compare_profile(
                            damaged_layers,
                            reference,
                            float(offset),
                            float(shift),
                            min_z,
                            last_z
                        )
                    )

                    if result is not None:

                        metrics[
                            piece
                        ] = result


                if len(metrics) != len(
                    references
                ):

                    continue


                winner = min(
                    metrics,
                    key=lambda p:
                        metrics[p][
                            "rmse"
                        ]
                )


                winner_counts[
                    range_name
                ][winner] += 1


                for piece, result in (
                    metrics.items()
                ):

                    output.append({

                        "range":
                            range_name,

                        "surface_offset_mm":
                            float(offset),

                        "z_shift_mm":
                            float(shift),

                        "piece":
                            piece,

                        "rmse_mm":
                            result["rmse"],

                        "mae_mm":
                            result["mae"],

                        "max_error_mm":
                            result[
                                "max_error"
                            ],

                        "points":
                            result["points"],

                        "winner":
                            int(
                                piece
                                == winner
                            )
                    })

    return (
        output,
        winner_counts
    )


def find_top_bottom(
    mask,
    center_x,
    half_window
):

    x0 = max(
        0,
        center_x
        - half_window
    )

    x1 = min(
        mask.shape[1],
        center_x
        + half_window
        + 1
    )

    region = (
        mask[:, x0:x1]
    )

    ys = np.where(
        region.any(axis=1)
    )[0]

    return (
        int(
            ys.min()
        ),
        int(
            ys.max()
        )
    )


def row_intervals(
    mask,
    y,
    x0,
    x1
):

    xs = np.where(
        mask[
            y,
            x0:x1
        ]
    )[0]

    xs = xs + x0


    if len(xs) == 0:

        return []


    intervals = []

    start = int(
        xs[0]
    )

    previous = int(
        xs[0]
    )


    for value in xs[1:]:

        value = int(value)

        if value > (
            previous + 1
        ):

            intervals.append(
                (
                    start,
                    previous
                )
            )

            start = value

        previous = value


    intervals.append(
        (
            start,
            previous
        )
    )

    return intervals


def calibration_half_width(
    edges,
    y,
    center_x,
    side,
    scale_x
):

    if side == "left":

        x0 = max(
            0,
            int(
                round(
                    center_x
                    - 230
                    * scale_x
                )
            )
        )

        x1 = int(
            round(
                center_x
                - 5
                * scale_x
            )
        )

        xs = np.where(
            edges[
                y,
                x0:x1
            ] > 0
        )[0]

        xs = xs + x0

        if len(xs) == 0:

            return None

        return (
            center_x
            - int(
                xs.min()
            )
        )


    if side == "right":

        x0 = int(
            round(
                center_x
                + 5
                * scale_x
            )
        )

        x1 = min(
            edges.shape[1],
            int(
                round(
                    center_x
                    + 231
                    * scale_x
                )
            )
        )

        xs = np.where(
            edges[
                y,
                x0:x1
            ] > 0
        )[0]

        xs = xs + x0

        if len(xs) == 0:

            return None

        return (
            int(
                xs.max()
            )
            - center_x
        )


    x0 = int(
        round(
            center_x
            + 15
            * scale_x
        )
    )

    x1 = min(
        edges.shape[1],
        int(
            round(
                center_x
                + 216
                * scale_x
            )
        )
    )

    xs = np.where(
        edges[
            y,
            x0:x1
        ] > 0
    )[0]

    xs = xs + x0


    if len(xs) == 0:

        return None


    return (
        int(
            xs.min()
        )
        - center_x
    )


def extract_upper_profiles(
    image_path,
    last_z
):

    image = cv2.imread(
        str(
            image_path
        )
    )

    if image is None:

        raise FileNotFoundError(
            image_path
        )


    image_h, image_w = (
        image.shape[:2]
    )


    scale_x = (
        image_w
        / BASE_IMAGE_W
    )

    scale_y = (
        image_h
        / BASE_IMAGE_H
    )


    gray = cv2.cvtColor(
        image,
        cv2.COLOR_BGR2GRAY
    )


    mask = (
        gray < 245
    )


    edges = cv2.Canny(
        gray,
        50,
        150
    )


    calibration_y = int(
        round(
            600
            * scale_y
        )
    )


    profiles = {}


    for piece, info in (
        PIECE_INFO.items()
    ):

        center_x = int(
            round(
                info["center_x"]
                * scale_x
            )
        )


        top_y, bottom_y = (
            find_top_bottom(
                mask,
                center_x,
                max(
                    10,
                    int(
                        round(
                            90
                            * scale_x
                        )
                    )
                )
            )
        )


        calibration_px = (
            calibration_half_width(
                edges,
                calibration_y,
                center_x,
                info["cal_side"],
                scale_x
            )
        )


        if (
            calibration_px is None
            or calibration_px <= 0
        ):

            raise RuntimeError(
                f"Calibration failed for {piece}"
            )


        mm_per_pixel = (
            15.0
            / calibration_px
        )


        crop_half = int(
            round(
                250
                * scale_x
            )
        )


        points = []


        for y in range(
            top_y,
            bottom_y + 1
        ):

            z = (
                (
                    bottom_y
                    - y
                )
                * info[
                    "height_mm"
                ]
                / (
                    bottom_y
                    - top_y
                )
            )


            if z < (
                last_z
                - 1.0
            ):

                continue


            x0 = max(
                0,
                center_x
                - crop_half
            )

            x1 = min(
                image_w,
                center_x
                + crop_half
                + 1
            )


            intervals = (
                row_intervals(
                    mask,
                    y,
                    x0,
                    x1
                )
            )


            if not intervals:

                continue


            containing = [
                interval
                for interval
                in intervals
                if (
                    interval[0]
                    <= center_x
                    <= interval[1]
                )
            ]


            if containing:

                interval = min(
                    containing,
                    key=lambda item:
                        abs(
                            (
                                item[0]
                                + item[1]
                            )
                            / 2.0
                            - center_x
                        )
                )

            else:

                interval = min(
                    intervals,
                    key=lambda item:
                        abs(
                            (
                                item[0]
                                + item[1]
                            )
                            / 2.0
                            - center_x
                        )
                )


                distance = min(
                    abs(
                        interval[0]
                        - center_x
                    ),

                    abs(
                        interval[1]
                        - center_x
                    )
                )


                if distance > int(
                    round(
                        30
                        * scale_x
                    )
                ):

                    continue


            if (
                interval[0]
                <= x0 + 1
                or
                interval[1]
                >= x1 - 2
            ):

                continue


            half_width_pixels = (
                interval[1]
                - interval[0]
                + 1
            ) / 2.0


            half_width_mm = (
                half_width_pixels
                * mm_per_pixel
            )


            points.append(
                (
                    z,
                    half_width_mm
                )
            )


        points = np.array(
            sorted(points),
            dtype=float
        )


        profiles[piece] = {

            "z":
                points[:, 0],

            "half_width":
                points[:, 1],

            "height_mm":
                info[
                    "height_mm"
                ],

            "mm_per_pixel":
                mm_per_pixel
        }


    return profiles


def save_upper_profiles(
    profiles,
    path
):

    rows = []

    for piece, data in (
        profiles.items()
    ):

        for z, width in zip(
            data["z"],
            data[
                "half_width"
            ]
        ):

            rows.append({
                "piece":
                    piece,

                "z_mm":
                    z,

                "half_width_mm":
                    width
            })


    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=[
                "piece",
                "z_mm",
                "half_width_mm"
            ]
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def empirical_extrusion_ratio(
    damaged_layers,
    number_of_layers=20
):

    candidates = []


    for row in damaged_layers:

        if row["z"] < 0.45:

            continue


        expected = (
            row[
                "square_path_expected"
            ]
        )


        if expected <= 0:

            continue


        path_ratio = (
            row["path"]
            / expected
        )


        if (
            0.98
            <= path_ratio
            <= 1.02
        ):

            candidates.append(
                row
            )


    candidates = sorted(
        candidates,
        key=lambda x:
            x["z"]
    )[
        -number_of_layers:
    ]


    if not candidates:

        raise RuntimeError(
            "Could not identify perimeter-only layers."
        )


    filament = sum(
        row["filament"]
        for row
        in candidates
    )


    path = sum(
        row["path"]
        for row
        in candidates
    )


    return (
        filament / path,
        candidates
    )


def predict_missing_filament(
    profiles,
    metadata,
    last_z,
    missing_budget,
    extrusion_ratio
):

    layer_height = (
        metadata[
            "layer_height_mm"
        ]
    )

    width = (
        metadata[
            "external_width_mm"
        ]
    )

    filament_diameter = (
        metadata[
            "filament_diameter_mm"
        ]
    )

    top_solid_layers = (
        metadata[
            "top_solid_layers"
        ]
    )


    filament_area = (
        math.pi
        * (
            filament_diameter
            / 2.0
        ) ** 2
    )


    results = []


    for piece, data in (
        profiles.items()
    ):

        final_height = (
            data[
                "height_mm"
            ]
        )


        z_layers = np.arange(
            last_z
            + layer_height,
            final_height,
            layer_height
        )


        z_layers = np.round(
            z_layers,
            5
        )


        surface_half_width = (
            np.interp(
                z_layers,
                data["z"],
                data[
                    "half_width"
                ]
            )
        )


        centerline_half_width = (
            np.maximum(
                surface_half_width
                - width / 2.0,
                0.0
            )
        )


        path_length = (
            8.0
            * centerline_half_width
        )


        perimeter_e = (
            path_length
            * extrusion_ratio
        )


        perimeter_total = float(
            perimeter_e.sum()
        )


        adjusted_e = (
            perimeter_e.copy()
        )


        if (
            top_solid_layers > 0
            and len(
                z_layers
            ) > 0
        ):

            start = max(
                0,
                len(z_layers)
                - top_solid_layers
            )


            indices = np.arange(
                start,
                len(z_layers)
            )


            full_solid_e = (
                (
                    (
                        2.0
                        * surface_half_width[
                            indices
                        ]
                    ) ** 2
                    * layer_height
                )
                / filament_area
            )


            adjusted_e[
                indices
            ] = np.maximum(
                adjusted_e[
                    indices
                ],
                full_solid_e
            )


        adjusted_total = float(
            adjusted_e.sum()
        )


        results.append({

            "piece":
                piece,

            "final_height_mm":
                final_height,

            "added_layers":
                len(z_layers),

            "predicted_missing_perimeter_mm":
                perimeter_total,

            "signed_error_perimeter_mm":
                perimeter_total
                - missing_budget,

            "abs_error_perimeter_mm":
                abs(
                    perimeter_total
                    - missing_budget
                ),

            "relative_error_perimeter_percent":
                abs(
                    perimeter_total
                    - missing_budget
                )
                / missing_budget
                * 100.0,

            "predicted_missing_topcap_adjusted_mm":
                adjusted_total,

            "abs_error_topcap_adjusted_mm":
                abs(
                    adjusted_total
                    - missing_budget
                ),

            "relative_error_topcap_adjusted_percent":
                abs(
                    adjusted_total
                    - missing_budget
                )
                / missing_budget
                * 100.0
        })


    return sorted(
        results,
        key=lambda x:
            x[
                "abs_error_perimeter_mm"
            ]
    )


def save_rows(
    rows,
    path
):

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=list(
                rows[0].keys()
            )
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def plot_geometry(
    damaged_layers,
    references,
    offset,
    path
):

    damaged_z = np.array([
        row["z"]
        for row
        in damaged_layers
        if row["z"] >= 0.45
    ])


    damaged_width = np.array([
        row[
            "half_centerline"
        ]
        + offset
        for row
        in damaged_layers
        if row["z"] >= 0.45
    ])


    plt.figure(
        figsize=(10, 7)
    )


    plt.plot(
        damaged_z,
        damaged_width,
        linewidth=3,
        label="Damaged G-code"
    )


    for piece, reference in (
        references.items()
    ):

        plt.plot(
            reference["z"],
            reference[
                "half_width"
            ],
            linewidth=1.5,
            label=piece
        )


    plt.xlabel(
        "Z height (mm)"
    )

    plt.ylabel(
        "Half width (mm)"
    )

    plt.title(
        "Damaged G-code vs Reference Profiles"
    )

    plt.legend()

    plt.grid(True)

    plt.tight_layout()

    plt.savefig(
        path,
        dpi=200
    )

    plt.close()


def plot_filament(
    results,
    missing_budget,
    path
):

    names = [
        row["piece"]
        for row
        in results
    ]

    predicted = [
        row[
            "predicted_missing_perimeter_mm"
        ]
        for row
        in results
    ]


    plt.figure(
        figsize=(8, 6)
    )


    plt.bar(
        names,
        predicted
    )


    plt.axhline(
        missing_budget,
        linestyle="--",
        label=(
            "Observed missing budget"
        )
    )


    plt.ylabel(
        "Missing filament (mm)"
    )

    plt.title(
        "Predicted Missing Filament"
    )

    plt.legend()

    plt.tight_layout()

    plt.savefig(
        path,
        dpi=200
    )

    plt.close()


def main():

    folder = (
        Path(__file__)
        .resolve()
        .parent
    )


    gcode_path = (
        folder
        / "damaged_chess.gcode"
    )

    clean_path = (
        folder
        / "clean_deposition.csv"
    )

    reference_path = (
        folder
        / "reference_profiles.csv"
    )

    image_path = (
        folder
        / "chess_pieces.png"
    )


    required = [
        gcode_path,
        clean_path,
        reference_path,
        image_path
    ]


    for path in required:

        if not path.exists():

            print(
                "Missing file:"
            )

            print(path)

            return


    metadata = (
        read_metadata(
            gcode_path
        )
    )


    deposition = (
        load_clean_deposition(
            clean_path
        )
    )


    existing_filament = sum(
        row["delta_e"]
        for row
        in deposition
    )


    missing_budget = (
        metadata[
            "filament_used_mm"
        ]
        - existing_filament
    )


    surface_offset = (
        metadata[
            "external_width_mm"
        ]
        / 2.0
    )


    damaged_layers = (
        build_damaged_layers(
            deposition,
            surface_offset
        )
    )


    save_damaged_layers(
        damaged_layers,
        folder
        / "damaged_layer_profile.csv"
    )


    comparison_layers = [
        row
        for row
        in damaged_layers
        if row["z"] >= 0.45
    ]


    last_z = max(
        row["z"]
        for row
        in comparison_layers
    )


    references = (
        load_reference_profiles(
            reference_path
        )
    )


    baseline = (
        baseline_geometry(
            comparison_layers,
            references,
            surface_offset,
            last_z
        )
    )


    save_rows(
        baseline,
        folder
        / "baseline_geometry_results.csv"
    )


    sensitivity_rows, winner_counts = (
        sensitivity_analysis(
            comparison_layers,
            references,
            last_z
        )
    )


    save_rows(
        sensitivity_rows,
        folder
        / "sensitivity_results.csv"
    )


    upper_profiles = (
        extract_upper_profiles(
            image_path,
            last_z
        )
    )


    save_upper_profiles(
        upper_profiles,
        folder
        / "upper_reference_profiles.csv"
    )


    extrusion_ratio, pure_layers = (
        empirical_extrusion_ratio(
            damaged_layers,
            20
        )
    )


    filament_results = (
        predict_missing_filament(
            upper_profiles,
            metadata,
            last_z,
            missing_budget,
            extrusion_ratio
        )
    )


    save_rows(
        filament_results,
        folder
        / "filament_prediction_results.csv"
    )


    plot_geometry(
        comparison_layers,
        references,
        surface_offset,
        folder
        / "geometry_comparison.png"
    )


    plot_filament(
        filament_results,
        missing_budget,
        folder
        / "filament_prediction.png"
    )


    print()

    print(
        "BASELINE GEOMETRY"
    )

    print(
        "=" * 75
    )


    for row in baseline:

        print(
            f"{row['piece']:10s} "
            f"RMSE = {row['rmse_mm']:.4f} mm   "
            f"MAE = {row['mae_mm']:.4f} mm   "
            f"MAX = {row['max_error_mm']:.4f} mm"
        )


    print()

    print(
        "SENSITIVITY ANALYSIS"
    )

    print(
        "=" * 75
    )


    for range_name, counts in (
        winner_counts.items()
    ):

        total = sum(
            counts.values()
        )

        print(
            range_name.upper()
        )

        for piece, count in sorted(
            counts.items(),
            key=lambda x:
                -x[1]
        ):

            percent = (
                count
                / total
                * 100.0
            )

            print(
                f"  {piece:10s} "
                f"{count:4d}/{total} "
                f"= {percent:6.2f}%"
            )


    print()

    print(
        "FILAMENT EVIDENCE"
    )

    print(
        "=" * 75
    )


    print(
        "Metadata total filament:",
        f"{metadata['filament_used_mm']:.5f} mm"
    )


    print(
        "Existing deposition:",
        f"{existing_filament:.5f} mm"
    )


    print(
        "Missing filament budget:",
        f"{missing_budget:.5f} mm"
    )


    print(
        "External perimeter width:",
        f"{metadata['external_width_mm']:.3f} mm"
    )


    print(
        "Layer height:",
        f"{metadata['layer_height_mm']:.3f} mm"
    )


    print(
        "Fill density:",
        f"{metadata['fill_density_percent']:.1f}%"
    )


    print(
        "Perimeters:",
        metadata["perimeters"]
    )


    print(
        "Empirical E/path ratio:",
        f"{extrusion_ratio:.8f}"
    )


    print(
        "Ratio validated using last",
        len(pure_layers),
        "perimeter-only layers"
    )


    print()


    for row in filament_results:

        print(
            f"{row['piece']:10s} "
            f"predicted = "
            f"{row['predicted_missing_perimeter_mm']:.2f} mm   "
            f"error = "
            f"{row['abs_error_perimeter_mm']:.2f} mm   "
            f"relative = "
            f"{row['relative_error_perimeter_percent']:.2f}%   "
            f"layers = "
            f"{row['added_layers']}"
        )


    print()

    print(
        "Best geometric match:",
        baseline[0]["piece"]
    )


    print(
        "Best filament match:",
        filament_results[0]["piece"]
    )


    print()

    print(
        "FILES CREATED"
    )

    print(
        "=" * 75
    )

    print(
        "damaged_layer_profile.csv"
    )

    print(
        "baseline_geometry_results.csv"
    )

    print(
        "sensitivity_results.csv"
    )

    print(
        "upper_reference_profiles.csv"
    )

    print(
        "filament_prediction_results.csv"
    )

    print(
        "geometry_comparison.png"
    )

    print(
        "filament_prediction.png"
    )


if __name__ == "__main__":

    main()
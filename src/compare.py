import csv
import math
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


MIN_Z = 0.45
MAX_Z = 23.95
SURFACE_OFFSET_MM = 0.25


def load_clean_deposition(path):
    rows = []

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append({
                "z": float(row["z"]),
                "x1": float(row["x1"]),
                "y1": float(row["y1"]),
                "x2": float(row["x2"]),
                "y2": float(row["y2"])
            })

    return rows


def build_damaged_profile(rows):
    layers = {}

    for row in rows:
        z = round(row["z"], 5)

        if z < MIN_Z or z > MAX_Z:
            continue

        if z not in layers:
            layers[z] = {
                "x": [],
                "y": []
            }

        layers[z]["x"].extend([
            row["x1"],
            row["x2"]
        ])

        layers[z]["y"].extend([
            row["y1"],
            row["y2"]
        ])

    profile = []

    for z in sorted(layers.keys()):
        xs = layers[z]["x"]
        ys = layers[z]["y"]

        xmin = min(xs)
        xmax = max(xs)

        ymin = min(ys)
        ymax = max(ys)

        center_x = (xmin + xmax) / 2.0
        center_y = (ymin + ymax) / 2.0

        half_width_x = (xmax - xmin) / 2.0
        half_width_y = (ymax - ymin) / 2.0

        half_width_centerline = (
            half_width_x + half_width_y
        ) / 2.0

        half_width_surface = (
            half_width_centerline
            + SURFACE_OFFSET_MM
        )

        profile.append({
            "z": z,
            "xmin": xmin,
            "xmax": xmax,
            "ymin": ymin,
            "ymax": ymax,
            "center_x": center_x,
            "center_y": center_y,
            "half_width_x": half_width_x,
            "half_width_y": half_width_y,
            "half_width": half_width_surface
        })

    return profile


def save_damaged_profile(profile, path):
    fields = [
        "z",
        "xmin",
        "xmax",
        "ymin",
        "ymax",
        "center_x",
        "center_y",
        "half_width_x",
        "half_width_y",
        "half_width"
    ]

    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields
        )

        writer.writeheader()
        writer.writerows(profile)


def load_reference_profiles(path):
    pieces = {}

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            piece = row["piece"]

            if piece not in pieces:
                pieces[piece] = {
                    "z": [],
                    "half_width": []
                }

            pieces[piece]["z"].append(
                float(row["z_mm"])
            )

            pieces[piece]["half_width"].append(
                float(row["half_width_mm"])
            )

    for piece in pieces:
        z = np.array(
            pieces[piece]["z"]
        )

        width = np.array(
            pieces[piece]["half_width"]
        )

        order = np.argsort(z)

        pieces[piece]["z"] = z[order]
        pieces[piece]["half_width"] = width[order]

    return pieces


def calculate_metrics(
    damaged_profile,
    reference_profiles
):
    damaged_z = np.array([
        row["z"]
        for row in damaged_profile
    ])

    damaged_width = np.array([
        row["half_width"]
        for row in damaged_profile
    ])

    results = {}

    for piece, data in reference_profiles.items():
        reference_z = data["z"]
        reference_width = data["half_width"]

        min_common_z = max(
            damaged_z.min(),
            reference_z.min()
        )

        max_common_z = min(
            damaged_z.max(),
            reference_z.max()
        )

        mask = (
            (damaged_z >= min_common_z)
            &
            (damaged_z <= max_common_z)
        )

        z_compare = damaged_z[mask]
        damaged_compare = damaged_width[mask]

        reference_interpolated = np.interp(
            z_compare,
            reference_z,
            reference_width
        )

        errors = (
            damaged_compare
            - reference_interpolated
        )

        rmse = math.sqrt(
            np.mean(errors ** 2)
        )

        mae = np.mean(
            np.abs(errors)
        )

        max_error = np.max(
            np.abs(errors)
        )

        results[piece] = {
            "rmse": rmse,
            "mae": mae,
            "max_error": max_error,
            "points": len(z_compare),
            "z": z_compare,
            "reference": reference_interpolated,
            "damaged": damaged_compare
        }

    return results


def save_results(results, path):
    with open(
        path,
        "w",
        newline="",
        encoding="utf-8"
    ) as f:

        writer = csv.writer(f)

        writer.writerow([
            "piece",
            "rmse_mm",
            "mae_mm",
            "max_error_mm",
            "comparison_points"
        ])

        for piece, result in sorted(
            results.items(),
            key=lambda item: item[1]["rmse"]
        ):
            writer.writerow([
                piece,
                result["rmse"],
                result["mae"],
                result["max_error"],
                result["points"]
            ])


def plot_profiles(
    damaged_profile,
    reference_profiles,
    output_path
):
    damaged_z = np.array([
        row["z"]
        for row in damaged_profile
    ])

    damaged_width = np.array([
        row["half_width"]
        for row in damaged_profile
    ])

    plt.figure(figsize=(10, 7))

    plt.plot(
        damaged_z,
        damaged_width,
        linewidth=3,
        label="Damaged G-code"
    )

    for piece, data in reference_profiles.items():
        mask = (
            (data["z"] >= MIN_Z)
            &
            (data["z"] <= MAX_Z)
        )

        plt.plot(
            data["z"][mask],
            data["half_width"][mask],
            linewidth=1.5,
            label=piece
        )

    plt.xlabel("Z height (mm)")
    plt.ylabel("Half width (mm)")
    plt.title(
        "Damaged G-code vs Reference Profiles"
    )

    plt.legend()
    plt.grid(True)
    plt.tight_layout()

    plt.savefig(
        output_path,
        dpi=200
    )

    plt.show()


def main():
    folder = Path(__file__).resolve().parent

    deposition_path = (
        folder /
        "clean_deposition.csv"
    )

    reference_path = (
        folder /
        "reference_profiles.csv"
    )

    damaged_profile_path = (
        folder /
        "damaged_profile.csv"
    )

    results_path = (
        folder /
        "comparison_results.csv"
    )

    plot_path = (
        folder /
        "profile_comparison.png"
    )

    if not deposition_path.exists():
        print(
            "Missing:",
            deposition_path
        )
        return

    if not reference_path.exists():
        print(
            "Missing:",
            reference_path
        )
        return

    deposition = load_clean_deposition(
        deposition_path
    )

    damaged_profile = build_damaged_profile(
        deposition
    )

    save_damaged_profile(
        damaged_profile,
        damaged_profile_path
    )

    reference_profiles = (
        load_reference_profiles(
            reference_path
        )
    )

    results = calculate_metrics(
        damaged_profile,
        reference_profiles
    )

    save_results(
        results,
        results_path
    )

    print()
    print("RESULTS")
    print("=" * 60)

    sorted_results = sorted(
        results.items(),
        key=lambda item: item[1]["rmse"]
    )

    for piece, result in sorted_results:
        print(
            f"{piece:10s} "
            f"RMSE = {result['rmse']:.4f} mm   "
            f"MAE = {result['mae']:.4f} mm   "
            f"MAX = {result['max_error']:.4f} mm"
        )

    print()
    print(
        "Best geometric match:",
        sorted_results[0][0]
    )

    print()
    print(
        "Damaged profile:",
        damaged_profile_path
    )

    print(
        "Comparison results:",
        results_path
    )

    plot_profiles(
        damaged_profile,
        reference_profiles,
        plot_path
    )


if __name__ == "__main__":
    main()
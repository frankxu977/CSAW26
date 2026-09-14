import csv
import math
from pathlib import Path
from dataclasses import dataclass


@dataclass
class State:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0
    absolute_xyz: bool = True
    absolute_e: bool = True

# delete annotation and empty space
def clean_line(line):
    return line.split(";", 1)[0].strip()

# find x y z e number
def get_value(parts, letter):
    for part in parts:
        if part.startswith(letter):
            try:
                return float(part[1:])
            except ValueError:
                return None
    return None

# Read the entire G-code, restore the printer's motion state, and then save only the extrusion move that actually occurred during printing.
def extract_deposition(gcode_path):
    state = State()
    rows = []
    epsilon = 1e-8

    with open(gcode_path, "r", encoding="utf-8", errors="ignore") as f:
        for line_number, raw_line in enumerate(f, start=1):
            line = clean_line(raw_line)

            if not line:
                continue

            parts = line.split()

            if not parts:
                continue

            command = parts[0]

            if command == "G90":
                state.absolute_xyz = True
                continue

            if command == "G91":
                state.absolute_xyz = False
                continue

            if command == "M82":
                state.absolute_e = True
                continue

            if command == "M83":
                state.absolute_e = False
                continue

            if command == "G92":
                x = get_value(parts, "X")
                y = get_value(parts, "Y")
                z = get_value(parts, "Z")
                e = get_value(parts, "E")

                if x is not None:
                    state.x = x
                if y is not None:
                    state.y = y
                if z is not None:
                    state.z = z
                if e is not None:
                    state.e = e

                continue

            if command not in ("G0", "G1"):
                continue

            old_x = state.x
            old_y = state.y
            old_z = state.z
            old_e = state.e

            x = get_value(parts, "X")
            y = get_value(parts, "Y")
            z = get_value(parts, "Z")
            e = get_value(parts, "E")

            if state.absolute_xyz:
                if x is not None:
                    state.x = x
                if y is not None:
                    state.y = y
                if z is not None:
                    state.z = z
            else:
                if x is not None:
                    state.x += x
                if y is not None:
                    state.y += y
                if z is not None:
                    state.z += z

            if e is not None:
                if state.absolute_e:
                    state.e = e
                    delta_e = state.e - old_e
                else:
                    delta_e = e
                    state.e += e
            else:
                delta_e = 0.0

            dx = state.x - old_x
            dy = state.y - old_y
            dz = state.z - old_z

            xy_distance = math.hypot(dx, dy)
            xyz_distance = math.sqrt(dx**2 + dy**2 + dz**2)

            if xy_distance > epsilon and delta_e > epsilon:
                rows.append({
                    "line": line_number,
                    "z": state.z,
                    "x1": old_x,
                    "y1": old_y,
                    "z1": old_z,
                    "x2": state.x,
                    "y2": state.y,
                    "z2": state.z,
                    "e1": old_e,
                    "e2": state.e,
                    "delta_e": delta_e,
                    "xy_distance": xy_distance,
                    "xyz_distance": xyz_distance
                })

    return rows


def save_csv(rows, output_path):
    fields = [
        "line",
        "z",
        "x1",
        "y1",
        "z1",
        "x2",
        "y2",
        "z2",
        "e1",
        "e2",
        "delta_e",
        "xy_distance",
        "xyz_distance"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main():
    folder = Path(__file__).resolve().parent

    gcode_path = folder / "damaged_chess.gcode"
    output_path = folder / "clean_deposition.csv"

    if not gcode_path.exists():
        print("File not found:")
        print(gcode_path)
        return

    rows = extract_deposition(gcode_path)

    save_csv(rows, output_path)

    total_filament = sum(row["delta_e"] for row in rows)
    z_levels = sorted(set(round(row["z"], 5) for row in rows))

    print("Deposition segments:", len(rows))
    print("Printing layers:", len(z_levels))
    print("First Z:", z_levels[0])
    print("Last Z:", z_levels[-1])
    print("Deposition filament:", total_filament)
    print("CSV saved to:")
    print(output_path)


if __name__ == "__main__":
    main()
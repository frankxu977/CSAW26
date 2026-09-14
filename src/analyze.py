import math
from dataclasses import dataclass
import matplotlib.pyplot as plt
from pathlib import Path

# ============================================================
# 1. 数据结构
# ============================================================

@dataclass
class PrinterState:
    """
    保存打印机当前状态
    """
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0

    # XYZ 是否为绝对坐标
    absolute_xyz: bool = True

    # E 是否为绝对坐标
    absolute_e: bool = True


@dataclass
class Segment:
    """
    保存一条 G0/G1 移动
    """
    x1: float
    y1: float
    z1: float
    e1: float

    x2: float
    y2: float
    z2: float
    e2: float

    delta_e: float
    xy_distance: float
    xyz_distance: float

    move_type: str

    line_number: int
    original_line: str


# ============================================================
# 2. 基础工具函数
# ============================================================

def remove_comment(line):
    """
    删除 G-code 中 ; 后面的注释

    例如：

    G1 X10 Y20 E3 ; print perimeter

    变成：

    G1 X10 Y20 E3
    """

    if ";" in line:
        line = line.split(";", 1)[0]

    return line.strip()


def get_parameter(parts, letter):
    """
    从 G-code token 中寻找参数

    例如：

    parts = ["G1", "X10.5", "Y20", "E3.2"]

    get_parameter(parts, "X")

    返回：

    10.5
    """

    for part in parts:

        if part.startswith(letter):

            try:
                return float(part[1:])

            except ValueError:
                return None

    return None


# ============================================================
# 3. G-code Parser
# ============================================================

def parse_gcode(filename):

    state = PrinterState()

    segments = []

    # 总 filament
    total_positive_e = 0.0

    # 真正 printing 使用的 filament
    deposition_filament = 0.0

    # retract 总量
    total_retraction = 0.0

    # 保存出现过的打印高度
    deposition_z_levels = set()

    with open(
        filename,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as file:

        for line_number, raw_line in enumerate(file, start=1):

            original_line = raw_line.rstrip("\n")

            line = remove_comment(raw_line)

            # 空行
            if not line:
                continue

            parts = line.split()

            if not parts:
                continue

            command = parts[0]


            # =================================================
            # G90
            # XYZ absolute positioning
            # =================================================

            if command == "G90":

                state.absolute_xyz = True

                continue


            # =================================================
            # G91
            # XYZ relative positioning
            # =================================================

            if command == "G91":

                state.absolute_xyz = False

                continue


            # =================================================
            # M82
            # Extruder absolute mode
            # =================================================

            if command == "M82":

                state.absolute_e = True

                continue


            # =================================================
            # M83
            # Extruder relative mode
            # =================================================

            if command == "M83":

                state.absolute_e = False

                continue


            # =================================================
            # G92
            # Set current position
            #
            # 例如：
            #
            # G92 E0
            #
            # 表示：
            #
            # 当前 E 坐标重新定义成 0
            # =================================================

            if command == "G92":

                new_x = get_parameter(parts, "X")
                new_y = get_parameter(parts, "Y")
                new_z = get_parameter(parts, "Z")
                new_e = get_parameter(parts, "E")

                if new_x is not None:
                    state.x = new_x

                if new_y is not None:
                    state.y = new_y

                if new_z is not None:
                    state.z = new_z

                if new_e is not None:
                    state.e = new_e

                continue


            # =================================================
            # 只处理 G0 / G1 移动
            # =================================================

            if command not in ("G0", "G1"):

                continue


            # =================================================
            # 保存旧坐标
            # =================================================

            old_x = state.x
            old_y = state.y
            old_z = state.z
            old_e = state.e


            # =================================================
            # 找出这一行提供了哪些参数
            # =================================================

            x_value = get_parameter(parts, "X")
            y_value = get_parameter(parts, "Y")
            z_value = get_parameter(parts, "Z")
            e_value = get_parameter(parts, "E")


            # =================================================
            # 更新 XYZ
            # =================================================

            if state.absolute_xyz:

                if x_value is not None:
                    state.x = x_value

                if y_value is not None:
                    state.y = y_value

                if z_value is not None:
                    state.z = z_value

            else:

                if x_value is not None:
                    state.x += x_value

                if y_value is not None:
                    state.y += y_value

                if z_value is not None:
                    state.z += z_value


            # =================================================
            # 更新 E
            # =================================================

            if e_value is not None:

                if state.absolute_e:

                    state.e = e_value

                    delta_e = state.e - old_e

                else:

                    delta_e = e_value

                    state.e += e_value

            else:

                delta_e = 0.0


            # =================================================
            # 计算移动距离
            # =================================================

            dx = state.x - old_x
            dy = state.y - old_y
            dz = state.z - old_z


            xy_distance = math.hypot(dx, dy)


            xyz_distance = math.sqrt(
                dx ** 2 +
                dy ** 2 +
                dz ** 2
            )


            # =================================================
            # 判断 move 类型
            # =================================================

            epsilon = 1e-8


            # -----------------------------------------------
            # Printing / deposition
            #
            # XY 有移动
            # 同时 E 增加
            # -----------------------------------------------

            if (
                xy_distance > epsilon
                and delta_e > epsilon
            ):

                move_type = "printing"

                deposition_filament += delta_e

                total_positive_e += delta_e

                deposition_z_levels.add(
                    round(state.z, 5)
                )


            # -----------------------------------------------
            # Retract
            # -----------------------------------------------

            elif delta_e < -epsilon:

                move_type = "retraction"

                total_retraction += abs(delta_e)


            # -----------------------------------------------
            # Extrusion without XY movement
            # -----------------------------------------------

            elif delta_e > epsilon:

                move_type = "extrusion_only"

                total_positive_e += delta_e


            # -----------------------------------------------
            # Travel
            # -----------------------------------------------

            elif xyz_distance > epsilon:

                move_type = "travel"


            else:

                move_type = "stationary"


            # =================================================
            # 保存 segment
            # =================================================

            segment = Segment(

                x1=old_x,
                y1=old_y,
                z1=old_z,
                e1=old_e,

                x2=state.x,
                y2=state.y,
                z2=state.z,
                e2=state.e,

                delta_e=delta_e,

                xy_distance=xy_distance,
                xyz_distance=xyz_distance,

                move_type=move_type,

                line_number=line_number,

                original_line=original_line
            )

            segments.append(segment)


    # ========================================================
    # 返回分析结果
    # ========================================================

    results = {

        "segments": segments,

        "total_positive_e": total_positive_e,

        "deposition_filament": deposition_filament,

        "total_retraction": total_retraction,

        "deposition_z_levels":
            sorted(deposition_z_levels),

        "final_state": state
    }

    return results


# ============================================================
# 4. 打印统计结果
# ============================================================

def print_statistics(results):

    segments = results["segments"]

    printing_segments = [
        s for s in segments
        if s.move_type == "printing"
    ]

    travel_segments = [
        s for s in segments
        if s.move_type == "travel"
    ]

    retract_segments = [
        s for s in segments
        if s.move_type == "retraction"
    ]


    z_levels = results["deposition_z_levels"]


    print()
    print("=" * 60)
    print("G-CODE ANALYSIS")
    print("=" * 60)


    print(
        "Total parsed moves:",
        len(segments)
    )


    print(
        "Printing segments:",
        len(printing_segments)
    )


    print(
        "Travel segments:",
        len(travel_segments)
    )


    print(
        "Retraction moves:",
        len(retract_segments)
    )


    print()


    print(
        "Deposition filament:",
        f"{results['deposition_filament']:.5f} mm"
    )


    print(
        "All positive E:",
        f"{results['total_positive_e']:.5f} mm"
    )


    print(
        "Total retraction:",
        f"{results['total_retraction']:.5f} mm"
    )


    print()


    print(
        "Number of deposition Z levels:",
        len(z_levels)
    )


    if z_levels:

        print(
            "First printing Z:",
            z_levels[0]
        )

        print(
            "Last printing Z:",
            z_levels[-1]
        )


    final_state = results["final_state"]


    print()

    print("Final machine state:")

    print(
        f"X = {final_state.x:.5f}"
    )

    print(
        f"Y = {final_state.y:.5f}"
    )

    print(
        f"Z = {final_state.z:.5f}"
    )

    print(
        f"E = {final_state.e:.5f}"
    )


    print("=" * 60)


# ============================================================
# 5. 提取真正的打印路径
# ============================================================

def get_printing_segments(results):

    return [

        segment

        for segment in results["segments"]

        if segment.move_type == "printing"
    ]


# ============================================================
# 6. XY 投影
#
# 从上面看棋子
# ============================================================

def plot_xy(printing_segments):

    plt.figure(figsize=(8, 8))

    for segment in printing_segments:

        plt.plot(

            [segment.x1, segment.x2],

            [segment.y1, segment.y2],

            linewidth=0.4
        )


    plt.xlabel("X (mm)")

    plt.ylabel("Y (mm)")

    plt.title(
        "XY Projection - Top View"
    )

    plt.axis("equal")

    plt.grid(True)

    plt.tight_layout()

    plt.show()


# ============================================================
# 7. XZ 投影
#
# 沿 Y 方向看
# ============================================================

def plot_xz(printing_segments):

    plt.figure(figsize=(10, 8))


    for segment in printing_segments:

        plt.plot(

            [segment.x1, segment.x2],

            [segment.z1, segment.z2],

            linewidth=0.4
        )


    plt.xlabel("X (mm)")

    plt.ylabel("Z (mm)")

    plt.title(
        "XZ Projection - Front View"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.show()


# ============================================================
# 8. YZ 投影
#
# 沿 X 方向看
# ============================================================

def plot_yz(printing_segments):

    plt.figure(figsize=(10, 8))


    for segment in printing_segments:

        plt.plot(

            [segment.y1, segment.y2],

            [segment.z1, segment.z2],

            linewidth=0.4
        )


    plt.xlabel("Y (mm)")

    plt.ylabel("Z (mm)")

    plt.title(
        "YZ Projection - Side View"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.show()


# ============================================================
# 9. 找每一层的信息
# ============================================================

def analyze_layers(printing_segments):

    layers = {}


    for segment in printing_segments:

        z = round(segment.z2, 5)


        if z not in layers:

            layers[z] = []


        layers[z].append(segment)


    return layers


# ============================================================
# 10. 输出 Layer 信息
# ============================================================

def print_layer_information(layers):

    print()
    print("=" * 60)

    print("LAYER INFORMATION")

    print("=" * 60)


    z_values = sorted(layers.keys())


    for z in z_values:

        layer = layers[z]


        filament = sum(

            s.delta_e

            for s in layer
        )


        path_length = sum(

            s.xy_distance

            for s in layer
        )


        print(

            f"Z = {z:7.3f} mm | "

            f"segments = {len(layer):4d} | "

            f"path = {path_length:9.3f} mm | "

            f"filament = {filament:8.4f} mm"
        )


# ============================================================
# 11. 寻找内部短 extrusion
#
# 这一步和报告中的隐藏 QR 分析有关
# ============================================================

def get_small_extrusion_runs(
    printing_segments,
    min_length=0.05,
    max_length=2.0
):

    small_segments = []


    for segment in printing_segments:

        length = segment.xy_distance


        if (
            min_length
            <= length
            <= max_length
        ):

            small_segments.append(segment)


    return small_segments


# ============================================================
# 12. 画短 extrusion 的 XZ 投影
#
# 有助于查看 QR 内部结构
# ============================================================

def plot_small_runs_xz(
    small_segments
):

    plt.figure(
        figsize=(10, 8)
    )


    for segment in small_segments:

        plt.plot(

            [segment.x1, segment.x2],

            [segment.z1, segment.z2],

            linewidth=1.0
        )


    plt.xlabel("X (mm)")

    plt.ylabel("Z (mm)")

    plt.title(
        "Small Extrusion Runs - XZ Projection"
    )

    plt.grid(True)

    plt.tight_layout()

    plt.show()


# ============================================================
# 13. 计算 Missing Filament
# ============================================================

def calculate_missing_filament(
    metadata_filament,
    parsed_filament
):

    missing = (
        metadata_filament
        -
        parsed_filament
    )

    return missing


# ============================================================
# 14. 主程序
# ============================================================

def main():

    script_folder = Path(__file__).resolve().parent
    filename = script_folder / "damaged_chess.gcode"

    print("Looking for G-code at:")
    print(filename)

    if not filename.exists():
        print("ERROR: G-code file not found.")
        print("Please put damaged_chess.gcode in the same folder as analyze.py:")
        print(script_folder)
        return

    # --------------------------------------------------------
    # Parse G-code
    # --------------------------------------------------------

    results = parse_gcode(filename)


    # --------------------------------------------------------
    # 打印统计
    # --------------------------------------------------------

    print_statistics(
        results
    )


    # --------------------------------------------------------
    # 提取 printing paths
    # --------------------------------------------------------

    printing_segments = (
        get_printing_segments(
            results
        )
    )


    # --------------------------------------------------------
    # Layer 分析
    # --------------------------------------------------------

    layers = analyze_layers(
        printing_segments
    )


    print_layer_information(
        layers
    )


    # --------------------------------------------------------
    # 根据报告中的 metadata filament
    #
    # Header:
    #
    # 4290.7 mm
    # --------------------------------------------------------

    metadata_filament = 4290.7


    parsed_filament = (
        results[
            "deposition_filament"
        ]
    )


    missing_filament = (
        calculate_missing_filament(

            metadata_filament,

            parsed_filament
        )
    )


    print()

    print(
        "Metadata filament:",
        metadata_filament,
        "mm"
    )


    print(
        "Parsed deposition filament:",
        f"{parsed_filament:.5f}",
        "mm"
    )


    print(
        "Estimated missing filament:",
        f"{missing_filament:.5f}",
        "mm"
    )


    # --------------------------------------------------------
    # 提取短 extrusion
    # --------------------------------------------------------

    small_runs = (
        get_small_extrusion_runs(
            printing_segments
        )
    )


    print()

    print(
        "Small extrusion segments:",
        len(small_runs)
    )


    # --------------------------------------------------------
    # 画图
    # --------------------------------------------------------

    plot_xy(
        printing_segments
    )


    plot_xz(
        printing_segments
    )


    plot_yz(
        printing_segments
    )


    plot_small_runs_xz(
        small_runs
    )


# ============================================================
# 15. 程序入口
# ============================================================

if __name__ == "__main__":

    main()
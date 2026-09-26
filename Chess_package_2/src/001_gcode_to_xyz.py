from pathlib import Path
import re


# 当前程序位于 chess_package/src
project_folder = Path(__file__).resolve().parent.parent

input_file = project_folder / "data" / "Raw" / "damaged_chess.gcode"
output_file = project_folder / "data" / "Processed" / "damaged_chess.xyz"

number_pattern = r"-?\d+(?:\.\d+)?"

x = 0.0
y = 0.0
z = 0.0
e = 0.0

point_count = 0


def read_value(line, letter, old_value):
    match = re.search(rf"\b{letter}({number_pattern})", line)

    if match:
        return float(match.group(1)), True

    return old_value, False


output_file.parent.mkdir(parents=True, exist_ok=True)

with input_file.open("r", encoding="utf-8", errors="ignore") as source:
    with output_file.open("w", encoding="utf-8") as output:

        for line in source:

            # G92 E0 表示重置挤出量
            if line.startswith("G92"):
                e, has_e = read_value(line, "E", e)
                continue

            # 只读取 G0 和 G1 移动命令
            if not line.startswith(("G0 ", "G1 ")):
                continue

            new_x, has_x = read_value(line, "X", x)
            new_y, has_y = read_value(line, "Y", y)
            new_z, has_z = read_value(line, "Z", z)
            new_e, has_e = read_value(line, "E", e)

            # E 增加代表打印机正在挤出材料
            if has_e and new_e > e and (has_x or has_y):
                output.write(f"{new_x} {new_y} {new_z}\n")
                point_count += 1

            x = new_x
            y = new_y
            z = new_z
            e = new_e


print("转换完成")
print("点数量：", point_count)
print("输出文件：", output_file)
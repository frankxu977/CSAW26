from pathlib import Path
import heapq

import cv2
import numpy as np


project_folder = Path(__file__).resolve().parent.parent

input_file = (
    project_folder
    / "data"
    / "Processed"
    / "loop_centers.xyz"
)

output_folder = (
    project_folder
    / "figures"
    / "calibrated_qr"
)

output_folder.mkdir(parents=True, exist_ok=True)

points = np.loadtxt(input_file)

x_values = points[:, 0]
z_values = points[:, 2]

SIZE = 21


# --------------------------------------------------
# 建立二维码中已知的固定模块
# --------------------------------------------------

known_modules = {}


def finder_value(row, column):
    outer = (
        row in (0, 6)
        or column in (0, 6)
    )

    center = (
        2 <= row <= 4
        and 2 <= column <= 4
    )

    return 1 if outer or center else 0


# 三个定位框
for start_row, start_column in [
    (0, 0),
    (0, 14),
    (14, 0),
]:
    for row in range(7):
        for column in range(7):
            known_modules[
                (
                    start_row + row,
                    start_column + column,
                )
            ] = finder_value(row, column)


# 三个定位框周围的白色分隔带
for column in range(8):
    known_modules[(7, column)] = 0
    known_modules[(13, column)] = 0

for row in range(8):
    known_modules[(row, 7)] = 0
    known_modules[(row, 13)] = 0

for column in range(13, 21):
    known_modules[(7, column)] = 0

for row in range(13, 21):
    known_modules[(row, 7)] = 0


# 时序线
for index in range(8, 13):
    expected = 1 if index % 2 == 0 else 0

    known_modules[(6, index)] = expected
    known_modules[(index, 6)] = expected


# 固定深色模块
known_modules[(13, 8)] = 1

known_positions = list(known_modules.keys())

expected_values = np.array(
    [
        known_modules[position]
        for position in known_positions
    ],
    dtype=np.uint8,
)


# --------------------------------------------------
# 根据参数统计每个模块中的闭合环数量
# --------------------------------------------------

def make_count_grid(
    start_x,
    bottom_z,
    module_size,
):
    counts = np.zeros(
        (SIZE, SIZE),
        dtype=np.int32,
    )

    columns = np.floor(
        (x_values - start_x) / module_size
    ).astype(int)

    rows = np.floor(
        (
            bottom_z
            + SIZE * module_size
            - z_values
        )
        / module_size
    ).astype(int)

    valid = (
        (columns >= 0)
        & (columns < SIZE)
        & (rows >= 0)
        & (rows < SIZE)
    )

    np.add.at(
        counts,
        (
            rows[valid],
            columns[valid],
        ),
        1,
    )

    return counts


def calibration_score(counts, threshold):
    predicted = np.array(
        [
            1 if counts[row, column] >= threshold else 0
            for row, column in known_positions
        ],
        dtype=np.uint8,
    )

    accuracy = (
        predicted == expected_values
    ).mean()

    black_counts = np.array(
        [
            counts[row, column]
            for row, column in known_positions
            if known_modules[(row, column)] == 1
        ],
        dtype=float,
    )

    white_counts = np.array(
        [
            counts[row, column]
            for row, column in known_positions
            if known_modules[(row, column)] == 0
        ],
        dtype=float,
    )

    separation = (
        black_counts.mean()
        - white_counts.mean()
    )

    return accuracy + separation * 0.002


# --------------------------------------------------
# 搜索网格起点、格子尺寸和计数阈值
# --------------------------------------------------

best_results = []

x_starts = np.arange(
    55.5,
    57.61,
    0.05,
)

z_bottoms = np.arange(
    5.5,
    7.31,
    0.05,
)

module_sizes = np.arange(
    0.52,
    0.691,
    0.01,
)

thresholds = range(1, 9)

total_combinations = (
    len(x_starts)
    * len(z_bottoms)
    * len(module_sizes)
)

tested = 0

print("开始校准21×21网格……")
print("网格组合数量：", total_combinations)


for module_size in module_sizes:
    for start_x in x_starts:
        for bottom_z in z_bottoms:
            counts = make_count_grid(
                start_x,
                bottom_z,
                module_size,
            )

            for threshold in thresholds:
                score = calibration_score(
                    counts,
                    threshold,
                )

                result = (
                    score,
                    float(start_x),
                    float(bottom_z),
                    float(module_size),
                    int(threshold),
                )

                if len(best_results) < 30:
                    heapq.heappush(
                        best_results,
                        result,
                    )
                elif score > best_results[0][0]:
                    heapq.heapreplace(
                        best_results,
                        result,
                    )

            tested += 1

    print(
        f"格子尺寸 {module_size:.2f} 已完成"
    )


best_results = sorted(
    best_results,
    reverse=True,
)

best_score, best_x, best_z, best_size, best_threshold = (
    best_results[0]
)

print()
print("最佳校准参数：")
print("得分：", best_score)
print("左边界 X：", best_x)
print("下边界 Z：", best_z)
print("模块尺寸：", best_size)
print("计数阈值：", best_threshold)


# --------------------------------------------------
# 恢复固定结构
# --------------------------------------------------

def restore_fixed_patterns(bits):
    bits = bits.copy()

    for position, value in known_modules.items():
        row, column = position
        bits[row, column] = value

    return bits


# --------------------------------------------------
# QR格式信息
# --------------------------------------------------

ERROR_LEVEL_BITS = {
    "L": 1,
    "M": 0,
    "Q": 3,
    "H": 2,
}


def make_format_bits(
    error_level,
    mask_number,
):
    data = (
        ERROR_LEVEL_BITS[error_level] << 3
    ) | mask_number

    remainder = data

    for _ in range(10):
        remainder <<= 1

        if remainder & (1 << 9):
            remainder ^= 0x537

    return (
        ((data << 10) | remainder)
        ^ 0x5412
    )


def write_format_bits(bits, format_value):
    bits = bits.copy()

    for index in range(15):
        value = (
            format_value >> index
        ) & 1

        if index <= 5:
            bits[index, 8] = value
        elif index == 6:
            bits[7, 8] = value
        elif index == 7:
            bits[8, 8] = value
        elif index == 8:
            bits[8, 7] = value
        else:
            bits[8, 14 - index] = value

        if index <= 7:
            bits[
                8,
                SIZE - 1 - index,
            ] = value
        else:
            bits[
                SIZE - 15 + index,
                8,
            ] = value

    bits[13, 8] = 1

    return bits


# --------------------------------------------------
# 生成标准二维码图片
# --------------------------------------------------

def render_qr(bits, scale=16):
    quiet_zone = 4

    modules = np.zeros(
        (
            SIZE + quiet_zone * 2,
            SIZE + quiet_zone * 2,
        ),
        dtype=np.uint8,
    )

    modules[
        quiet_zone:quiet_zone + SIZE,
        quiet_zone:quiet_zone + SIZE,
    ] = bits

    image = 255 - modules * 255

    return cv2.resize(
        image.astype(np.uint8),
        None,
        fx=scale,
        fy=scale,
        interpolation=cv2.INTER_NEAREST,
    )


def transformations(bits):
    for rotation in range(4):
        rotated = np.rot90(
            bits,
            rotation,
        )

        yield (
            f"rotation_{rotation * 90}",
            rotated,
        )

        yield (
            f"rotation_{rotation * 90}_mirror",
            np.fliplr(rotated),
        )


# --------------------------------------------------
# 对最佳30组校准结果进行自动解码
# --------------------------------------------------

detector = cv2.QRCodeDetector()

found = False
attempts = 0


for rank, result in enumerate(
    best_results,
    start=1,
):
    (
        score,
        start_x,
        bottom_z,
        module_size,
        threshold,
    ) = result

    counts = make_count_grid(
        start_x,
        bottom_z,
        module_size,
    )

    base_bits = (
        counts >= threshold
    ).astype(np.uint8)

    base_bits = restore_fixed_patterns(
        base_bits
    )

    # 保存每个校准结果的基础候选图
    base_image = render_qr(base_bits)

    cv2.imwrite(
        str(
            output_folder
            / f"calibration_{rank:02d}.png"
        ),
        base_image,
    )

    for error_level in ["L", "M", "Q", "H"]:
        for mask_number in range(8):
            format_value = make_format_bits(
                error_level,
                mask_number,
            )

            formatted_bits = write_format_bits(
                base_bits,
                format_value,
            )

            for transform_name, transformed in transformations(
                formatted_bits
            ):
                attempts += 1

                image = render_qr(
                    transformed
                )

                text, corners, _ = (
                    detector.detectAndDecode(
                        image
                    )
                )

                if text:
                    found = True

                    result_image = (
                        output_folder
                        / "decoded_qr.png"
                    )

                    result_text = (
                        output_folder
                        / "decoded_text.txt"
                    )

                    cv2.imwrite(
                        str(result_image),
                        image,
                    )

                    result_text.write_text(
                        text,
                        encoding="utf-8",
                    )

                    print()
                    print("解码成功！")
                    print("内容：", text)
                    print("校准排名：", rank)
                    print("X起点：", start_x)
                    print("Z起点：", bottom_z)
                    print("模块尺寸：", module_size)
                    print("计数阈值：", threshold)
                    print("纠错等级：", error_level)
                    print("掩码：", mask_number)
                    print("变换：", transform_name)
                    print("二维码：", result_image)

                    break

            if found:
                break

        if found:
            break

    if found:
        break

    print(
        f"校准候选 {rank}/30 未解码"
    )


if not found:
    print()
    print("校准完成，但仍未自动解码。")
    print("尝试次数：", attempts)
    print(
        "请查看 calibrated_qr 文件夹中的 "
        "calibration_01.png 到 calibration_30.png。"
    )
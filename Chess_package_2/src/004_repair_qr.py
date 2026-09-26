from pathlib import Path
import sys
import itertools

import cv2
import numpy as np

try:
    from reedsolo import RSCodec, ReedSolomonError
except ImportError:
    print("缺少 reedsolo。先运行：")
    print("python -m pip install reedsolo")
    sys.exit(1)


# ============================================================
# QR Version 1 基本参数
# ============================================================

QR_SIZE = 21

# Version 1 不同纠错等级
# 总 codewords 永远是 26
EC_INFO = {
    "L": {"data": 19, "ecc": 7},
    "M": {"data": 16, "ecc": 10},
    "Q": {"data": 13, "ecc": 13},
    "H": {"data": 9,  "ecc": 17},
}

# format information 里的编码
EC_FORMAT_BITS = {
    "L": 1,
    "M": 0,
    "Q": 3,
    "H": 2,
}

ALPHANUMERIC_TABLE = (
    "0123456789"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " $%*+-./:"
)


# ============================================================
# 从 PNG 提取 21 × 21 QR matrix
# 黑 = 1
# 白 = 0
# ============================================================

def load_qr_matrix(image_path):
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)

    if image is None:
        raise FileNotFoundError(f"无法读取图片：{image_path}")

    _, binary = cv2.threshold(
        image,
        0,
        255,
        cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )

    # 找黑色像素
    ys, xs = np.where(binary < 128)

    if len(xs) == 0:
        raise ValueError("图片里没有找到黑色 QR module。")

    x_min = xs.min()
    x_max = xs.max()
    y_min = ys.min()
    y_max = ys.max()

    width = x_max - x_min + 1
    height = y_max - y_min + 1

    module_w = width / QR_SIZE
    module_h = height / QR_SIZE

    print()
    print("========== 图像分析 ==========")
    print("图片尺寸:", image.shape[::-1])
    print("QR 黑色区域:", width, "x", height)
    print("估计 module:", module_w, "x", module_h)

    matrix = np.zeros(
        (QR_SIZE, QR_SIZE),
        dtype=np.uint8
    )

    for r in range(QR_SIZE):
        for c in range(QR_SIZE):

            # 每个格子的中心区域采样
            x1 = int(x_min + (c + 0.25) * module_w)
            x2 = int(x_min + (c + 0.75) * module_w)

            y1 = int(y_min + (r + 0.25) * module_h)
            y2 = int(y_min + (r + 0.75) * module_h)

            block = binary[y1:y2, x1:x2]

            if block.size == 0:
                continue

            black_ratio = np.mean(block < 128)

            matrix[r, c] = 1 if black_ratio >= 0.5 else 0

    return matrix


# ============================================================
# 打印 21 × 21 matrix
# ============================================================

def print_matrix(matrix):
    print()
    print("========== 21 x 21 QR Matrix ==========")

    for row in matrix:
        print(
            "".join(
                "██" if value else "  "
                for value in row
            )
        )


# ============================================================
# QR format information
# ============================================================

def make_format_bits(ec_level, mask):
    """
    生成合法的 QR format information。
    QR 使用 BCH(15,5)，最后 XOR 0x5412。
    """

    data = (
        (EC_FORMAT_BITS[ec_level] << 3)
        | mask
    )

    remainder = data

    for _ in range(10):
        remainder = (
            (remainder << 1)
            ^ (
                (remainder >> 9)
                * 0x537
            )
        )

    return (
        ((data << 10) | remainder)
        ^ 0x5412
    )


def format_positions():
    """
    QR 有两份 format information。
    返回：
    copy1
    copy2

    bit 顺序是 bit 0 → bit 14
    """

    copy1 = [
        (0, 8),
        (1, 8),
        (2, 8),
        (3, 8),
        (4, 8),
        (5, 8),

        (7, 8),
        (8, 8),
        (8, 7),

        (8, 5),
        (8, 4),
        (8, 3),
        (8, 2),
        (8, 1),
        (8, 0),
    ]

    copy2 = []

    # row 8，右边
    for i in range(8):
        copy2.append(
            (8, 20 - i)
        )

    # column 8，下面
    for i in range(7):
        copy2.append(
            (14 + i, 8)
        )

    return copy1, copy2


def read_format_bits(matrix):
    copy1_positions, copy2_positions = format_positions()

    results = []

    for positions in [
        copy1_positions,
        copy2_positions
    ]:

        value = 0

        for bit_index, (r, c) in enumerate(positions):
            value |= (
                int(matrix[r, c])
                << bit_index
            )

        results.append(value)

    return results


def hamming_distance(a, b):
    return (a ^ b).bit_count()


def rank_format_candidates(matrix):
    """
    返回全部 32 种 EC + mask，
    按照和图片 format information 的距离排序。
    """

    read1, read2 = read_format_bits(matrix)

    candidates = []

    for ec_level in EC_INFO:
        for mask in range(8):

            expected = make_format_bits(
                ec_level,
                mask
            )

            d1 = hamming_distance(
                read1,
                expected
            )

            d2 = hamming_distance(
                read2,
                expected
            )

            candidates.append({
                "ec": ec_level,
                "mask": mask,
                "distance1": d1,
                "distance2": d2,
                "total": d1 + d2,
                "format": expected,
            })

    candidates.sort(
        key=lambda x: x["total"]
    )

    return candidates


# ============================================================
# 标记 QR Function Modules
#
# Finder
# Separator
# Timing
# Format
# Dark Module
# ============================================================

def function_module_mask():
    function = np.zeros(
        (QR_SIZE, QR_SIZE),
        dtype=bool
    )

    def mark_finder(cx, cy):

        # Finder 7x7 + 周围 separator
        # 一共约 9x9 区域
        for dy in range(-4, 5):
            for dx in range(-4, 5):

                x = cx + dx
                y = cy + dy

                if (
                    0 <= x < QR_SIZE
                    and
                    0 <= y < QR_SIZE
                ):
                    function[y, x] = True

    mark_finder(3, 3)
    mark_finder(QR_SIZE - 4, 3)
    mark_finder(3, QR_SIZE - 4)

    # Timing patterns
    function[6, :] = True
    function[:, 6] = True

    # Format information
    p1, p2 = format_positions()

    for r, c in p1 + p2:
        function[r, c] = True

    # Dark module
    # Version 1:
    # row = 4 * version + 9 = 13
    function[13, 8] = True

    return function


# ============================================================
# QR Mask Pattern
# ============================================================

def should_mask(mask_number, r, c):

    if mask_number == 0:
        return (r + c) % 2 == 0

    if mask_number == 1:
        return r % 2 == 0

    if mask_number == 2:
        return c % 3 == 0

    if mask_number == 3:
        return (r + c) % 3 == 0

    if mask_number == 4:
        return (
            (r // 2)
            +
            (c // 3)
        ) % 2 == 0

    if mask_number == 5:
        return (
            (r * c) % 2
            +
            (r * c) % 3
        ) == 0

    if mask_number == 6:
        return (
            (
                (r * c) % 2
                +
                (r * c) % 3
            )
            % 2
        ) == 0

    if mask_number == 7:
        return (
            (
                (r + c) % 2
                +
                (r * c) % 3
            )
            % 2
        ) == 0

    raise ValueError(
        f"未知 mask：{mask_number}"
    )


# ============================================================
# Zig-zag 读取 data modules
# ============================================================

def extract_codewords(matrix, mask_number):

    function = function_module_mask()

    bits = []
    module_positions = []

    right = QR_SIZE - 1
    upward = True

    while right >= 1:

        # column 6 是 timing pattern
        if right == 6:
            right -= 1

        if upward:
            row_range = range(
                QR_SIZE - 1,
                -1,
                -1
            )
        else:
            row_range = range(
                QR_SIZE
            )

        for r in row_range:

            for c in [
                right,
                right - 1
            ]:

                if function[r, c]:
                    continue

                bit = int(
                    matrix[r, c]
                )

                # unmask
                if should_mask(
                    mask_number,
                    r,
                    c
                ):
                    bit ^= 1

                bits.append(bit)

                module_positions.append(
                    (r, c)
                )

        upward = not upward
        right -= 2

    if len(bits) != 208:
        raise ValueError(
            f"应该有 208 data bits，实际得到 {len(bits)}"
        )

    codewords = []

    for i in range(
        0,
        len(bits),
        8
    ):

        value = 0

        for bit in bits[i:i + 8]:
            value = (
                (value << 1)
                | bit
            )

        codewords.append(value)

    return (
        codewords,
        bits,
        module_positions
    )


# ============================================================
# Reed-Solomon
# ============================================================

def try_reed_solomon(
    codewords,
    ec_level
):

    ecc_count = EC_INFO[
        ec_level
    ]["ecc"]

    codec = RSCodec(
        ecc_count
    )

    try:

        result = codec.decode(
            bytearray(codewords)
        )

        # 新版 reedsolo 返回 tuple：
        #
        # (
        #   decoded_data,
        #   corrected_message_and_ecc,
        #   error_positions
        # )

        if isinstance(
            result,
            tuple
        ):

            decoded_data = bytes(
                result[0]
            )

            corrected_full = (
                bytes(result[1])
                if len(result) >= 2
                else None
            )

            error_positions = (
                list(result[2])
                if len(result) >= 3
                else []
            )

        else:
            decoded_data = bytes(
                result
            )

            corrected_full = None
            error_positions = []

        return {
            "success": True,
            "data": decoded_data,
            "corrected": corrected_full,
            "errors": error_positions,
        }

    except ReedSolomonError:
        return {
            "success": False
        }

    except Exception:
        return {
            "success": False
        }


# ============================================================
# Bit Reader
# ============================================================

class BitReader:

    def __init__(self, data):
        self.bits = []

        for byte in data:
            for i in range(7, -1, -1):
                self.bits.append(
                    (byte >> i)
                    & 1
                )

        self.position = 0

    def remaining(self):
        return (
            len(self.bits)
            -
            self.position
        )

    def read(self, count):

        if self.remaining() < count:
            raise ValueError(
                "bitstream 不够长"
            )

        value = 0

        for _ in range(count):
            value = (
                value << 1
            ) | self.bits[
                self.position
            ]

            self.position += 1

        return value


# ============================================================
# QR Payload Parser
# 支持：
# Numeric
# Alphanumeric
# Byte
# ============================================================

def parse_payload(data):

    reader = BitReader(data)

    output = []

    while reader.remaining() >= 4:

        mode = reader.read(4)

        # terminator
        if mode == 0:
            break

        # -------------------------------
        # Numeric
        # -------------------------------

        if mode == 0b0001:

            if reader.remaining() < 10:
                raise ValueError(
                    "Numeric count 损坏"
                )

            count = reader.read(10)

            if count > 100:
                raise ValueError(
                    f"不合理 Numeric count: {count}"
                )

            text = ""

            while count >= 3:

                value = reader.read(10)

                if value > 999:
                    raise ValueError(
                        "Numeric 数据非法"
                    )

                text += f"{value:03d}"
                count -= 3

            if count == 2:
                value = reader.read(7)

                if value > 99:
                    raise ValueError(
                        "Numeric 数据非法"
                    )

                text += f"{value:02d}"

            elif count == 1:

                value = reader.read(4)

                if value > 9:
                    raise ValueError(
                        "Numeric 数据非法"
                    )

                text += str(value)

            output.append(text)

        # -------------------------------
        # Alphanumeric
        # -------------------------------

        elif mode == 0b0010:

            if reader.remaining() < 9:
                raise ValueError(
                    "Alphanumeric count 损坏"
                )

            count = reader.read(9)

            # Version 1 最大不可能很夸张
            if count > 50:
                raise ValueError(
                    f"不合理 Alphanumeric count: {count}"
                )

            text = ""

            while count >= 2:

                value = reader.read(11)

                first = value // 45
                second = value % 45

                if (
                    first >= 45
                    or
                    second >= 45
                ):
                    raise ValueError(
                        "Alphanumeric 数据非法"
                    )

                text += (
                    ALPHANUMERIC_TABLE[first]
                    +
                    ALPHANUMERIC_TABLE[second]
                )

                count -= 2

            if count == 1:

                value = reader.read(6)

                if value >= 45:
                    raise ValueError(
                        "Alphanumeric 数据非法"
                    )

                text += (
                    ALPHANUMERIC_TABLE[value]
                )

            output.append(text)

        # -------------------------------
        # Byte
        # -------------------------------

        elif mode == 0b0100:

            if reader.remaining() < 8:
                raise ValueError(
                    "Byte count 损坏"
                )

            count = reader.read(8)

            if count > 50:
                raise ValueError(
                    f"不合理 Byte count: {count}"
                )

            raw = bytearray()

            for _ in range(count):
                raw.append(
                    reader.read(8)
                )

            try:
                text = raw.decode(
                    "utf-8"
                )

            except UnicodeDecodeError:

                text = raw.decode(
                    "latin-1"
                )

            output.append(text)

        else:
            raise ValueError(
                f"暂不支持/非法 mode: {mode:04b}"
            )

    return "".join(output)


# ============================================================
# 尝试正常 QR RS 解码
# ============================================================

def try_candidate(
    matrix,
    ec_level,
    mask_number
):

    codewords, bits, positions = (
        extract_codewords(
            matrix,
            mask_number
        )
    )

    rs = try_reed_solomon(
        codewords,
        ec_level
    )

    if not rs["success"]:
        return None

    try:
        text = parse_payload(
            rs["data"]
        )

    except Exception:
        return None

    if not text:
        return None

    return {
        "text": text,
        "ec": ec_level,
        "mask": mask_number,
        "codewords": codewords,
        "bits": bits,
        "positions": positions,
        "rs": rs,
    }


# ============================================================
# 在正常 RS 纠错之外，再尝试翻转 1 / 2 个 data bit
#
# 原因：
# Version 1-Q 可以纠正最多 6 个错误 codeword。
#
# 如果实际上有 7 个错误 codeword，
# 先猜对一个坏 bit，
# 剩余 6 个就可能交给 RS 自动修复。
# ============================================================

def brute_force_extra_bits(
    matrix,
    ec_level,
    mask_number,
    max_extra_flips=2
):

    codewords, bits, positions = (
        extract_codewords(
            matrix,
            mask_number
        )
    )

    print()
    print(
        "开始额外 bit 修复：",
        ec_level,
        "mask",
        mask_number
    )

    print(
        "原始 codewords:"
    )

    print(
        " ".join(
            f"{x:02X}"
            for x in codewords
        )
    )

    # ------------------------------------------------
    # 先尝试翻 1 bit
    # ------------------------------------------------

    if max_extra_flips >= 1:

        print()
        print(
            "尝试额外翻转 1 bit..."
        )

        for bit_index in range(208):

            modified = list(
                codewords
            )

            byte_index = (
                bit_index // 8
            )

            bit_inside_byte = (
                bit_index % 8
            )

            mask_value = (
                1
                <<
                (
                    7
                    -
                    bit_inside_byte
                )
            )

            modified[
                byte_index
            ] ^= mask_value

            rs = try_reed_solomon(
                modified,
                ec_level
            )

            if not rs["success"]:
                continue

            try:
                text = parse_payload(
                    rs["data"]
                )

            except Exception:
                continue

            if text:

                return {
                    "text": text,
                    "ec": ec_level,
                    "mask": mask_number,
                    "extra_flips": [
                        bit_index
                    ],
                    "positions": [
                        positions[
                            bit_index
                        ]
                    ],
                    "rs": rs,
                }

    # ------------------------------------------------
    # 再尝试翻 2 bit
    # ------------------------------------------------

    if max_extra_flips >= 2:

        print()
        print(
            "尝试额外翻转 2 bit..."
        )

        total = (
            208 * 207 // 2
        )

        checked = 0

        for first in range(208):

            for second in range(
                first + 1,
                208
            ):

                checked += 1

                if checked % 2500 == 0:
                    print(
                        f"  {checked}/{total}"
                    )

                modified = list(
                    codewords
                )

                for bit_index in [
                    first,
                    second
                ]:

                    byte_index = (
                        bit_index // 8
                    )

                    bit_inside = (
                        bit_index % 8
                    )

                    modified[
                        byte_index
                    ] ^= (
                        1
                        <<
                        (
                            7
                            -
                            bit_inside
                        )
                    )

                rs = try_reed_solomon(
                    modified,
                    ec_level
                )

                if not rs["success"]:
                    continue

                try:
                    text = parse_payload(
                        rs["data"]
                    )

                except Exception:
                    continue

                if text:

                    return {
                        "text": text,
                        "ec": ec_level,
                        "mask": mask_number,
                        "extra_flips": [
                            first,
                            second
                        ],
                        "positions": [
                            positions[first],
                            positions[second]
                        ],
                        "rs": rs,
                    }

    return None


# ============================================================
# 8 种方向
# ============================================================

def transformations(matrix):

    result = []

    for k in range(4):

        rotated = np.rot90(
            matrix,
            k
        )

        result.append(
            (
                f"rotate_{k * 90}",
                rotated.copy()
            )
        )

        result.append(
            (
                f"rotate_{k * 90}_mirror",
                np.fliplr(
                    rotated
                ).copy()
            )
        )

    return result


# ============================================================
# 找输入图片
# ============================================================

def find_default_image():

    script_path = Path(
        __file__
    ).resolve()

    project_root = (
        script_path.parent.parent
    )

    candidates = [
        project_root
        / "calibrated_qr"
        / "calibration_01.png",

        script_path.parent
        / "calibrated_qr"
        / "calibration_01.png",

        Path.cwd()
        / "calibrated_qr"
        / "calibration_01.png",

        Path.cwd()
        / "calibration_01.png",
    ]

    for path in candidates:

        if path.exists():
            return path

    return None


# ============================================================
# Main
# ============================================================

def main():

    # 可以：
    #
    # python repair_qr.py calibration_01.png
    #
    # 不传参数则自动寻找 calibrated_qr

    if len(sys.argv) >= 2:

        image_path = Path(
            sys.argv[1]
        ).resolve()

    else:

        image_path = (
            find_default_image()
        )

        if image_path is None:

            print(
                "找不到 calibration_01.png"
            )

            print(
                "请运行："
            )

            print(
                'python src/repair_qr.py "完整图片路径"'
            )

            return

    print(
        "读取：",
        image_path
    )

    original = load_qr_matrix(
        image_path
    )

    print_matrix(
        original
    )

    # ========================================================
    # STEP 1:
    # 所有方向 + 所有 EC/mask
    # 先让 RS 正常尝试
    # ========================================================

    print()
    print(
        "=========================================="
    )

    print(
        "STEP 1：尝试标准 Reed-Solomon 解码"
    )

    print(
        "=========================================="
    )

    all_format_candidates = []

    for transform_name, matrix in transformations(
        original
    ):

        ranked = rank_format_candidates(
            matrix
        )

        best = ranked[0]

        print()
        print(
            transform_name,
            "最佳 format:"
        )

        print(
            " EC =",
            best["ec"]
        )

        print(
            " Mask =",
            best["mask"]
        )

        print(
            " Format distance =",
            best["distance1"],
            "+",
            best["distance2"],
            "=",
            best["total"]
        )

        all_format_candidates.append(
            (
                best["total"],
                transform_name,
                matrix,
                ranked
            )
        )

        # 不完全相信损坏的 format，
        # 所以这里全部 32 种都试。
        for candidate in ranked:

            result = try_candidate(
                matrix,
                candidate["ec"],
                candidate["mask"]
            )

            if result:

                print()
                print(
                    "=========================================="
                )

                print(
                    "成功！"
                )

                print(
                    "=========================================="
                )

                print(
                    "方向:",
                    transform_name
                )

                print(
                    "纠错等级:",
                    result["ec"]
                )

                print(
                    "Mask:",
                    result["mask"]
                )

                print(
                    "RS 修复位置:",
                    result["rs"]["errors"]
                )

                print()
                print(
                    "二维码内容："
                )

                print(
                    result["text"]
                )

                return

    # ========================================================
    # STEP 2:
    # 图片 format 最可信的组合
    # 再猜额外 1~2 个坏 bit
    # ========================================================

    print()
    print(
        "标准 Reed-Solomon 无法直接恢复。"
    )

    all_format_candidates.sort(
        key=lambda x: x[0]
    )

    (
        best_distance,
        best_transform_name,
        best_matrix,
        ranked
    ) = all_format_candidates[0]

    best_format = ranked[0]

    print()
    print(
        "=========================================="
    )

    print(
        "STEP 2：对最佳候选额外尝试 bit 修复"
    )

    print(
        "=========================================="
    )

    print(
        "方向:",
        best_transform_name
    )

    print(
        "EC:",
        best_format["ec"]
    )

    print(
        "Mask:",
        best_format["mask"]
    )

    print(
        "Format distance:",
        best_format["distance1"],
        "+",
        best_format["distance2"]
    )

    result = brute_force_extra_bits(
        best_matrix,
        best_format["ec"],
        best_format["mask"],
        max_extra_flips=2
    )

    if result:

        print()
        print(
            "=========================================="
        )

        print(
            "修复成功！"
        )

        print(
            "=========================================="
        )

        print(
            "EC:",
            result["ec"]
        )

        print(
            "Mask:",
            result["mask"]
        )

        print(
            "额外修改 bits:",
            result["extra_flips"]
        )

        print(
            "对应 QR 坐标:",
            result["positions"]
        )

        print(
            "RS 修复位置:",
            result["rs"]["errors"]
        )

        print()
        print(
            "二维码内容："
        )

        print(
            result["text"]
        )

        return

    # ========================================================
    # FAIL
    # ========================================================

    print()
    print(
        "=========================================="
    )

    print(
        "目前仍然无法恢复"
    )

    print(
        "=========================================="
    )

    print()
    print(
        "这说明损坏已经超过："
    )

    print(
        "标准 Reed-Solomon + 额外 2 bit 搜索"
    )

    print()
    print(
        "最佳 format 判断为："
    )

    print(
        "EC:",
        best_format["ec"]
    )

    print(
        "Mask:",
        best_format["mask"]
    )

    print(
        "Format copy #1 错误 bit 数:",
        best_format["distance1"]
    )

    print(
        "Format copy #2 错误 bit 数:",
        best_format["distance2"]
    )

    codewords, _, _ = extract_codewords(
        best_matrix,
        best_format["mask"]
    )

    print()
    print(
        "当前提取出的 26 个 codewords："
    )

    print(
        " ".join(
            f"{value:02X}"
            for value in codewords
        )
    )

    print()
    print(
        "下一步应该利用 damaged_chess.gcode "
        "判断哪些 module/codeword 是损坏位置，"
        "然后作为 Reed-Solomon erasure 处理。"
    )


if __name__ == "__main__":
    main()
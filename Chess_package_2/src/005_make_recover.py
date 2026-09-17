from pathlib import Path

import qrcode


# ============================================================
# Project paths
#
# Chess_package_2/
# ├── figures/
# │   └── recovered_qr.png
# └── src/
#     └── make_recover.py
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIGURES_DIR = PROJECT_ROOT / "figures"

OUTPUT_FILE = FIGURES_DIR / "recovered_qr.png"


# Create the output folder if it does not exist
FIGURES_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# Recovered QR content
# ============================================================

TEXT = "is.gd/19hak3"


# ============================================================
# Generate the recovered QR code
# ============================================================

qr = qrcode.QRCode(
    version=1,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=20,
    border=4,
    mask_pattern=2,
)

qr.add_data(TEXT)

qr.make(
    fit=False
)


# ============================================================
# Render and save the QR image
# ============================================================

image = qr.make_image(
    fill_color="black",
    back_color="white",
)

image.save(
    OUTPUT_FILE
)


# ============================================================
# Final status
# ============================================================

print("Recovered QR generated successfully.")
print("QR content:", TEXT)
print("Output file:", OUTPUT_FILE)
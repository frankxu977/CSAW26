# Damaged G-code QR Recovery

This project recovers a hidden QR code from a damaged 3D-printing G-code file.

## Workflow

### 1. Initial Inspection

The damaged G-code was first inspected using **UltiMaker Cura** and **CloudCompare** to visualize the 3D structure and locate the hidden pattern.

[![Step 1](figures/1.png)](figures/1.png)

[![Step 2](figures/2.png)](figures/2.png)

[![Step 3](figures/3.png)](figures/3.png)

### 2. Convert G-code to XYZ

[`001_gcode_to_xyz.py`](src/001_gcode_to_xyz.py)

Extracts extrusion coordinates from:

```text
src/Raw/damaged_chess.gcode
```

and generates:

```text
data/001_damaged_chess.xyz
```

### 3. Find the QR Viewing Angle

[`002_angle_scan.py`](src/002_angle_scan.py)

The 3D point cloud is projected from different angles to reveal the hidden QR structure.

[![3D Model](figures/3D.png)](figures/3D.png)

### 4. Calibrate the QR Grid

[`003_calibrate_qr_grid.py`](src/003_calibrate_qr_grid.py)

Uses `loop_centers.xyz` to reconstruct a Version 1 QR code with a `21 × 21` module grid.

[![Original QR](figures/qr_code_original.png)](figures/qr_code_original.png)

### 5. Repair the QR Code

[`004_repair_qr.py`](src/004_repair_qr.py)

The damaged QR data is recovered using QR format analysis and Reed-Solomon error correction.

Recovered result:

```text
Error Correction: M
Mask: 2
Payload: is.gd/19hak3
```

### 6. Generate the Final QR

[`005_make_recover.py`](src/005_make_recover.py)

Generates a clean QR code from the recovered payload.

[![Recovered QR](figures/recovered_qr.png)](figures/recovered_qr.png)

## Result

Recovered QR content:

```text
is.gd/19hak3
```

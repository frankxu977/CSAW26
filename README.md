# Challenge 2 — Gear CAD Recovery

## Overview

The goal of Challenge 2 was to recover the hidden CAD models from four provided images.

Although the four images looked similar at first, they required four different recovery methods:

1. **Image 0119** — Recover a direct Google Drive CAD link from the JPG data.
2. **Image 0338** — Recover a manufacturer link and download the CAD model from McMaster-Carr.
3. **Image 1139** — Solve an engineering riddle about the gear pressure angle.
4. **Image 2161** — Decode a Caesar cipher to obtain the archive password.

---

# 1. Image 0119 — Direct CAD Retrieval

## Method

For Image 0119, I first opened `Ball_rec0119.jpg` in **HxD Hex Editor** instead of only viewing the image normally.

Because useful information can be stored inside a JPG file without appearing in the visible image, I searched the raw file data for:

```text
https://drive.google.com
```

A readable Google Drive URL appeared starting at:

```text
Decimal offset:     2152
Hexadecimal offset: 0x868
```

The URL was stored directly as readable text inside the JPG data.

After recovering the full URL and opening it in a browser, it led directly to the CAD model.

## Key Idea

The JPG itself was being used as a container for hidden text.

The CAD model did not need to be reconstructed manually, and there was no password or cipher to solve. The important step was inspecting the binary contents of the image rather than only looking at the image visually.

## Result

**CAD model recovered directly from the hidden Google Drive link.**

This was the shortest and most direct recovery method of the four.

---

# 2. Image 0338 — Manufacturer CAD Download

## Method

Image 0338 was more complicated because it contained **two different hidden URLs**.

I opened `Ball_rec0338.jpg` in HxD and inspected the file contents.

### Google Drive Link

The first link was a Google Drive URL.

It appeared as readable text around:

```text
Decimal offset:     2152
Hexadecimal offset: 0x868
```

The Google Drive route provided:

```text
Downloaded Gear_2.7z
```

which contained:

```text
Downloaded Gear.zip
```

However, extracting this archive did not give me a usable model during the investigation.

Instead of continuing to attack the archive, I inspected the JPG for other clues.

### McMaster-Carr Link

A second URL appeared later in the JPG at:

```text
Decimal offset:     4266
Hexadecimal offset: 0x10AA
```

This link was different because it was encoded using **UTF-16LE**.

In a normal single-byte hex view, UTF-16LE text looks similar to:

```text
h.t.t.p...
```

because many characters have a `00` byte between them.

After decoding the text, the URL pointed to a McMaster-Carr product page.

The important information recovered from the link was the part number:

```text
2664N443
```

McMaster-Carr provides downloadable CAD models for many mechanical components. I searched for this part and used the product page's **CAD download** option to obtain the model directly from the manufacturer.

## Key Idea

Unlike Image 0119, the first recovered link was not the most useful solution.

The important step was realizing that the JPG contained another hidden link encoded differently.

Instead of trying to repair or crack the nested archive, the manufacturer part number provided a much easier and more reliable path to the CAD model.

## Result

**CAD model recovered from the McMaster-Carr product page for part `2664N443`.**

The supplied Google Drive archive was not required as the final working source.

---

# 3. Image 1139 — Pressure-Angle Riddle

## Method

The recovery path for Image 1139 was different from the first two.

The linked Google Drive folder contained:

```text
Original SLDPRT.7z
Riddle.txt
```

Instead of directly providing the archive password, `Riddle.txt` asked:

```text
What is the pressure angle of this gear in degrees?
```

This meant the password clue was based on **gear engineering knowledge** rather than hidden binary text.

The pressure angle is an important parameter in involute gear geometry. A very common standard pressure angle for modern gears is:

```text
20 degrees
```

Using this value solved the riddle.

## Key Idea

This route required interpreting an engineering clue.

The solution was not another URL hidden in the file. The challenge expected the user to understand or identify a standard gear parameter and use that value as the password clue.

## Result

```text
Pressure angle = 20 degrees
```

The riddle therefore resolves to:

```text
20
```

This value provides the password clue for accessing the original SolidWorks part archive.

---

# 4. Image 2161 — Caesar Cipher

## Method

Image 2161 used a cryptography-based clue.

The associated Google Drive folder contained:

```text
Original STL.7z
```

and the clue:

```text
Cesar had a pass time of writing secret messages to his generals
```

followed by:

```text
Ybsbidbxo
```

The reference to **Caesar** and secret military messages strongly suggested a **Caesar cipher**.

A Caesar cipher shifts every letter by a fixed number of positions in the alphabet.

For this message, shifting each ciphertext letter **forward by 3 positions** gives:

```text
Ciphertext: Y b s b i d b x o
             ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓ ↓
Plaintext:  B e v e l g e a r
```

Therefore:

```text
Ybsbidbxo
```

decodes to:

```text
Bevelgear
```

or conceptually:

```text
Bevel gear
```

The decoded text provides the password clue for:

```text
Original STL.7z
```
Key idea

The important clue was the wording about **Caesar** and secret messages.

Instead of interpreting "Cesar" as a Roman-number clue, I treated it as a reference to the Caesar substitution cipher.

Applying a shift of three recovered a meaningful mechanical term, confirming that the decoding method was correct.

## Result

```text
Ybsbidbxo → Bevelgear
```

The recovered password clue is:

```text
Bevelgear
```

---

# Comparison of the Four Recovery Methods

| Image | Main Technique | Hidden Information | Final Recovery Method |
|------|----------------|-------------------|----------------------|
| **0119** | Hex inspection | Google Drive URL | Download CAD directly |
| **0338** | Hex inspection + UTF-16LE | McMaster-Carr product link | Download manufacturer CAD |
| **1139** | Gear engineering knowledge | Pressure-angle riddle | Solve with **20°** |
| **2161** | Cryptography | `Ybsbidbxo` | Caesar shift → `Bevelgear` |

---

"""ocr.py IMG [WORD]  -> prints the text seen on screen; with WORD prints 'x y' (screen pixels) of its first match."""
import subprocess, sys
img, word = sys.argv[1], (sys.argv[2].lower() if len(sys.argv) > 2 else None)
subprocess.run(["convert", img, "-resize", "200%", "-colorspace", "Gray", "-negate", "/tmp/ocr.png"], check=True)
tsv = subprocess.run(["tesseract", "/tmp/ocr.png", "stdout", "--psm", "11", "tsv"], capture_output=True, text=True).stdout
words = []
for l in tsv.splitlines()[1:]:
    p = l.split("\t")
    if len(p) == 12 and p[11].strip():
        x, y, w, h = map(int, p[6:10])
        words.append((p[11].strip(), (x + w / 2) / 2, (y + h / 2) / 2))
if word is None:
    print("OCR:", " | ".join(f"{t}@{int(x)},{int(y)}" for t, x, y in words))
else:
    for t, x, y in words:
        if word in t.lower():
            print(int(x), int(y)); break
    else:
        sys.exit(1)

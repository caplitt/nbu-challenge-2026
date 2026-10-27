"""Layout check of the exported deck: finds text that collides with other text (two boxes overlapping, bullets
running into the footer), text lying on a picture, and text off the slide. Works on the PDF, i.e. on what is actually
rendered, not on the estimates deck/build_deck.js uses to size the boxes.

    soffice --headless --convert-to pdf --outdir presentation presentation/NBU_University_Challenge_2026.pptx
    python deck/check_layout.py presentation/NBU_University_Challenge_2026.pdf     # prints TOTAL 0 when clean

Text running over the edge of a card or into empty space is not detected — look at the slides as well."""
import sys, pdfplumber

def inter(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0]); h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0

def area(a):
    return max(a[2] - a[0], 0) * max(a[3] - a[1], 0)

pdf = pdfplumber.open(sys.argv[1])
total = 0
for pno, page in enumerate(pdf.pages, 1):
    W, H = page.width, page.height
    words = page.extract_words(use_text_flow=False, keep_blank_chars=False, extra_attrs=["size"])
    boxes = [(w["x0"], w["top"], w["x1"], w["bottom"], w["text"], w["size"]) for w in words]
    issues = []
    # word-on-word: different words whose boxes intersect substantially (shrink a bit to tolerate tight leading)
    sh = [(b[0] + 0.3, b[1] + 1.0, b[2] - 0.3, b[3] - 1.0, b[4]) for b in boxes]
    for i in range(len(sh)):
        for j in range(i + 1, len(sh)):
            a, b = sh[i], sh[j]
            vh = min(a[3], b[3]) - max(a[1], b[1]); hw = min(a[2], b[2]) - max(a[0], b[0])
            if vh > 0.2 * min(a[3] - a[1], b[3] - b[1]) and hw > 1.5:
                issues.append(f"text/text: «{a[4]}» ↔ «{b[4]}» at y≈{a[1]:.0f}")
    # text over images
    for im in page.images:
        ib = (im["x0"], im["top"], im["x1"], im["bottom"])
        for b in sh:
            if inter(b, ib) > 0.3 * area(b):
                issues.append(f"text/image: «{b[4]}» at y≈{b[1]:.0f}")
    # off page
    for b in boxes:
        if b[0] < -1 or b[2] > W + 1 or b[3] > H + 1:
            issues.append(f"off-page: «{b[4]}»")
    if issues:
        uniq = list(dict.fromkeys(issues))
        total += len(uniq)
        print(f"--- slide {pno}: {len(uniq)} issue(s)")
        for s in uniq[:12]:
            print("   ", s)
        if len(uniq) > 12:
            print(f"    … +{len(uniq) - 12}")
print("TOTAL", total)
sys.exit(1 if total else 0)

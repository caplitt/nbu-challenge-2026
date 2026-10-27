// Збирає презентацію з deck/deck_data.json (створює deck/content.py).
// Запуск з кореня репозиторію:  node deck/build_deck.js
const path = require("path");
const fs = require("fs");
const pptxgen = require("pptxgenjs");

const ROOT = path.resolve(__dirname, "..");
const DATA = JSON.parse(fs.readFileSync(path.join(__dirname, "deck_data.json"), "utf8"));
const OUT_DIR = path.join(ROOT, "presentation");
const OUT = path.join(OUT_DIR, "NBU_University_Challenge_2026.pptx");
// writes THEME colours/name into the deck's theme part (pptxgenjs cannot); vendored from the pptx skill
const APPLY_THEME = path.join(__dirname, "apply_theme.js");

// ------------------------------------------------------------------ theme (deep teal + hryvnia gold)
const THEME = {
  name: "NBU Challenge 2026",
  headFontFace: "Cambria",
  bodyFontFace: "Calibri",
  colors: {
    dk1: "1B2326", lt1: "FFFFFF", dk2: "0E3B43", lt2: "EAF1EF",
    accent1: "0E3B43", accent2: "C98A00", accent3: "2A78D6", accent4: "EB6834",
    accent5: "1BAF7A", accent6: "5F6B6D", hlink: "2A78D6", folHlink: "4A3AA7",
  },
};
const HEX = { teal: "0E3B43", gold: "C98A00", tint: "EAF1EF", tint2: "D5E4E0", ink: "1B2326",
  muted: "5F6B6D", grid: "C9D6D3", white: "FFFFFF", up: "C0392B", down: "1E8449" };

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.title = "Рекомендації щодо монетарної політики — NBU University Challenge 2026";
pres.author = DATA.team.name;
const C = pres.SchemeColor;
const W = 13.333, H = 7.5, M = 0.5;

// ------------------------------------------------------------------ layouts
function breadcrumbObjects(current) {
  // one text object per section label: masters accept plain strings only, not styled runs
  const objs = [];
  let x = M;
  DATA.sections.forEach((s, i) => {
    const label = (i < 3 ? `${i + 1} ` : "") + s;
    const on = s === current;
    const w = 0.08 * label.length + 0.25;
    objs.push({ text: { text: label, options: { x, y: H - 0.42, w, h: 0.3, fontSize: 10, bold: on,
      color: on ? HEX.teal : HEX.muted, fontFace: THEME.bodyFontFace, margin: 0 } } });
    x += w + 0.2;
  });
  return objs;
}
const titleOpts = { x: M, y: 0.3, w: W - 2 * M, h: 1.0, fontFace: THEME.headFontFace, fontSize: 26, bold: true,
  color: C.accent1, valign: "top", align: "left", margin: 0 };
for (const sec of [null, ...DATA.sections]) {
  pres.defineSlideMaster({
    title: "CONTENT_" + (sec || "intro"),
    background: { color: "FFFFFF" },
    margin: [0.4, 0.5, 0.55, 0.5],
    objects: [
      { placeholder: { options: { name: "title", type: "title", ...titleOpts }, text: "" } },
      ...(sec ? breadcrumbObjects(sec) : [{ text: { text: "NBU University Challenge 2026", options: { x: M, y: H - 0.42,
        w: 6, h: 0.3, fontSize: 10, color: HEX.muted, fontFace: THEME.bodyFontFace, margin: 0 } } }]),
    ],
    slideNumber: { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.3, fontSize: 10, color: C.accent6, align: "right",
      fontFace: THEME.bodyFontFace },
  });
}
pres.defineSlideMaster({
  title: "DARK",
  background: { color: HEX.teal },
  objects: [
    { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.6, w: 11.7, h: 1.4, fontFace: THEME.headFontFace,
      fontSize: 40, bold: true, color: C.background1, valign: "top", align: "left", margin: 0 }, text: "" } },
  ],
});

// ------------------------------------------------------------------ text fitting
// pptxgenjs does not measure text, and PowerPoint/LibreOffice do not shrink an overfull box when the file is opened,
// so every box is sized here from an estimate of its wrapped height. Widths are average advances per character in em,
// measured on the exported PDF (26.10.2026): body Calibri/Carlito 0.48 median (the greedy wrap estimate already
// overcounts lines, so the median is used; checked with a collision test on the PDF); headings in Cambria
// render in LibreOffice with DejaVu Serif for Cyrillic (Caladea has no Cyrillic), 0.68 median -> 0.66 for the greedy
// estimate (it overcounts wraps; checked on the rendered titles: all two-line titles fit at 26 pt). Line pitch 1.2 of the font size, as measured.
const EM_BODY = 0.48, EM_HEAD = 0.66, LINE = 1.2;
const OVERFLOW = [];
function wrapLines(text, size, widthIn, em = EM_BODY) {
  const cpl = Math.max(4, Math.floor(widthIn / (size / 72 * em)));
  let lines = 0;
  for (const para of String(text).split("\n")) {
    let cur = 0; lines += 1;
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const L = word.length;
      if (cur === 0) cur = L; else if (cur + 1 + L <= cpl) cur += 1 + L; else { lines += 1; cur = L; }
      while (cur > cpl) { lines += 1; cur -= cpl; }
    }
  }
  return lines;
}
// height (in) of a list of paragraphs: indent = bullet indent (in), paraAfter = space after a paragraph (pt)
function textHeight(items, size, widthIn, { indent = 0, paraAfter = 0, em = EM_BODY } = {}) {
  const arr = Array.isArray(items) ? items : [items];
  const lines = arr.reduce((a, t) => a + wrapLines(plain(t), size, widthIn - indent, em), 0);
  return lines * size * LINE / 72 + Math.max(arr.length - 1, 0) * paraAfter / 72;
}
// largest font size (step 0.5 pt) between `min` and `size` at which the text fits; records a warning if none does
function fitSize(items, widthIn, heightIn, size, min, opts = {}, where = "") {
  let s = size;
  while (s > min && textHeight(items, s, widthIn, opts) > heightIn) s -= 0.5;
  if (process.env.DECK_DEBUG && s < size) console.log(`  [${s} з ${size}] ${where}`);
  if (textHeight(items, s, widthIn, opts) > heightIn + 0.01) OVERFLOW.push(`${where}: потрібно ${textHeight(items, s,
    widthIn, opts).toFixed(2)} in, є ${heightIn.toFixed(2)} in`);
  return s;
}
const BULLET = { indent: 14 / 72, paraAfter: 8 };
let CURRENT = "";   // title of the slide being built, for warnings

// ------------------------------------------------------------------ helpers
function image(slide, im, x, y, maxW, maxH, name) {
  const ar = im.w / im.h;
  let w = maxW, h = maxW / ar;
  if (h > maxH) { h = maxH; w = maxH * ar; }
  slide.addImage({ path: im.path, x, y, w, h, objectName: name || "chart" });
  return { x, y, w, h };
}
function bulletsBox(slide, items, x, y, w, h, size = 14, min = 11) {
  if (!items || !items.length) return size;
  const fs_ = fitSize(items, w, h, size, min, BULLET, `${CURRENT} — пункти`);
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < items.length - 1,
    paraSpaceAfter: 8 } })), { x, y, w, h, fontSize: fs_, color: C.text1, valign: "top", margin: 0, isTextBox: true,
    objectName: "bullets" });
  return fs_;
}
function numberedRow(slide, items, x, y, w, h) {
  const n = items.length, gap = 0.3, cw = (w - gap * (n - 1)) / n;
  // one size for the whole row, so the points look alike
  const fs_ = Math.min(...items.map((t, i) => fitSize(t, cw - 0.45, h, 13, 10.5, {}, `${CURRENT} — пункт ${i + 1}`)));
  items.forEach((t, i) => {
    const cx = x + i * (cw + gap);
    slide.addShape(pres.shapes.OVAL, { x: cx, y: y + 0.02, w: 0.34, h: 0.34, fill: { color: HEX.gold }, line: { type: "none" },
      objectName: `num${i + 1}` });
    slide.addText(String(i + 1), { x: cx, y: y + 0.02, w: 0.34, h: 0.34, fontSize: 12, bold: true, color: C.background1,
      align: "center", valign: "middle", margin: 0, isTextBox: true });
    slide.addText(t, { x: cx + 0.45, y, w: cw - 0.45, h, fontSize: fs_, color: C.text1, valign: "top", margin: 0,
      isTextBox: true, objectName: `point${i + 1}` });
  });
}
// a cell / source is a string, a {text, url} link, or a list of them (runs); links become clickable hyperlinks
function runs(c) {
  const one = (r) => (r && typeof r === "object")
    ? (r.url ? { text: r.text, options: { hyperlink: { url: r.url, tooltip: r.url } } } : { text: r.text })
    : { text: String(r) };
  return Array.isArray(c) ? c.map(one) : (c && typeof c === "object") ? [one(c)] : String(c);
}
function plain(c) {
  return Array.isArray(c) ? c.map(plain).join("") : (c && typeof c === "object") ? c.text : String(c);
}
function sourcesLine(slide, sources) {
  if (!sources || !sources.length) return;
  const items = [{ text: "Джерела: " }];
  sources.forEach((s, i) => { if (i) items.push({ text: " · " }); items.push(s); });
  // one line between the breadcrumb and the slide number: shrink rather than wrap onto the slide body
  const sw = W - M - 0.75 - 5.4;
  const fs_ = fitSize(plain(items), sw, 9 * LINE / 72 + 0.005, 9, 7, {}, `${CURRENT} — джерела`);
  slide.addText(runs(items), { x: 5.4, y: H - 0.44, w: sw, h: 0.32, fontSize: fs_, color: HEX.muted,
    valign: "middle", margin: 0, isTextBox: true, objectName: "sources" });
}
function table(slide, t, x, y, w, opts = {}) {
  const fs_ = t.font || opts.font || 12;
  const header = t.header.map((h) => ({ text: h, options: { bold: true, color: C.background1, fill: { color: HEX.teal },
    fontSize: fs_, valign: "middle" } }));
  const rows = t.rows.map((r, ri) => r.map((c, ci) => {
    const align = ci === 0 ? "left" : (opts.leftAll ? "left" : "center");
    // every run needs the cell's align: pptxgenjs starts a new paragraph when align differs between runs
    const txt = runs(c);
    const text = Array.isArray(txt) ? txt.map((x) => ({ text: x.text, options: { ...(x.options || {}), align } })) : txt;
    return { text, options: { fontSize: fs_, color: C.text1, fill: { color: ri % 2 ? HEX.tint : "FFFFFF" },
      bold: ci === 0 || plain(c).includes("★"), align, valign: "middle" } };
  }));
  const colW = t.colw || (() => { const first = opts.firstCol || Math.min(3.2, w * 0.32);
    const rest = (w - first) / (t.header.length - 1); return [first, ...Array(t.header.length - 1).fill(rest)]; })();
  const rh = t.rowH || opts.rowH;
  const extra = rh ? { rowH: rh } : {};
  slide.addTable([header, ...rows], { x, y, w, colW, border: { type: "solid", pt: 0.5, color: HEX.grid },
    margin: [3, 5, 3, 5], autoPage: false, objectName: "table", ...extra });
  return tableHeight(t, colW, fs_, rh || 0);
}
// estimated table height (in): each row is as tall as its tallest wrapped cell (cell margins 3 + 3 pt, 5 + 5 pt)
function tableHeight(t, colW, fs_, rowH) {
  const rowOf = (r, bold) => Math.max(rowH, ...r.map((c, ci) =>
    wrapLines(plain(c), fs_, colW[ci] - 10 / 72, bold ? EM_BODY * 1.06 : EM_BODY) * fs_ * LINE / 72 + 6 / 72));
  return rowOf(t.header, true) + t.rows.reduce((a, r) => a + rowOf(r, false), 0);
}
function colWidths(t, w, opts = {}) {
  if (t.colw) return t.colw;
  const first = opts.firstCol || Math.min(3.2, w * 0.32);
  const rest = (w - first) / (t.header.length - 1);
  return [first, ...Array(t.header.length - 1).fill(rest)];
}
// largest table font (from `size` down to `min`) at which the table fits into `maxH`
function fitTable(t, w, maxH, size, min, opts = {}) {
  const colW = colWidths(t, w, opts);
  let s = size;
  while (s > min && tableHeight(t, colW, s, opts.rowH || t.rowH || 0) > maxH) s -= 0.5;
  if (tableHeight(t, colW, s, opts.rowH || t.rowH || 0) > maxH + 0.02) OVERFLOW.push(`${CURRENT} — таблиця`);
  return s;
}
function newSlide(s) {
  CURRENT = s.title;
  const master = s.section ? "CONTENT_" + s.section : "CONTENT_intro";
  const slide = pres.addSlide({ masterName: master, sectionTitle: s.section || "Вступ" });
  // the title box holds two lines at 26 pt; a longer title is shrunk instead of running into the slide body
  const tfs = fitSize(s.title, W - 2 * M, 1.0, 26, 20, { em: EM_HEAD }, `${s.title} — заголовок`);
  slide.addText(s.title, { placeholder: "title", fontSize: tfs });
  if (s.notes) slide.addNotes(s.notes);
  sourcesLine(slide, s.sources);
  return slide;
}
const TOP = 1.45, BOTTOM = H - 0.6;

// ------------------------------------------------------------------ renderers
const R = {
  title(s) {
    const slide = pres.addSlide({ masterName: "DARK", sectionTitle: "Вступ" });
    slide.addText(s.title, { placeholder: "title" });
    slide.addText(s.subtitle, { x: 0.8, y: 4.05, w: 11.7, h: 0.6, fontSize: 22, color: HEX.gold, bold: true, margin: 0,
      isTextBox: true, fontFace: THEME.headFontFace });
    slide.addText(s.meta.map((m, i) => ({ text: m, options: { breakLine: i < s.meta.length - 1 } })),
      { x: 0.8, y: 5.3, w: 11.7, h: 1.2, fontSize: 16, color: C.background1, margin: 0, isTextBox: true, paraSpaceAfter: 4 });
    if (s.notes) slide.addNotes(s.notes);
  },
  section(s) {
    const slide = pres.addSlide({ masterName: "DARK", sectionTitle: s.section });
    slide.addText(s.title, { placeholder: "title" });
    if (s.number) slide.addText(s.number, { x: 0.8, y: 1.4, w: 3, h: 1.1, fontSize: 60, bold: true, color: HEX.gold,
      fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    if (s.subtitle) slide.addText(s.subtitle, { x: 0.8, y: 4.1, w: 11.7, h: 0.8, fontSize: 18, color: "CFE3DE", margin: 0,
      isTextBox: true });
  },
  summary(s) {
    const slide = newSlide(s);
    const n = s.cards.length, gap = 0.3, cw = (W - 2 * M - gap * (n - 1)) / n, ch = 2.3;
    // one text size for all cards: the longest card text decides
    const cfs = Math.min(...s.cards.map((c) => fitSize(c.text, cw - 0.5, ch - 1.4, 13, 10.5, {}, `${CURRENT} — картка`)));
    s.cards.forEach((c, i) => {
      const x = M + i * (cw + gap), y = TOP;
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.08, fill: { color: HEX.tint },
        line: { type: "none" }, objectName: `card${i + 1}` });
      slide.addText(c.label.toUpperCase(), { x: x + 0.25, y: y + 0.18, w: cw - 0.5, h: 0.3, fontSize: 11, bold: true,
        color: C.accent6, charSpacing: 1, margin: 0, isTextBox: true });
      slide.addText([{ text: c.value, options: { fontSize: 40, bold: true, color: C.accent1, fontFace: THEME.headFontFace } },
        { text: "  " + c.delta, options: { fontSize: 15, bold: true, color: HEX.gold } }],
        { x: x + 0.25, y: y + 0.5, w: cw - 0.5, h: 0.8, valign: "middle", margin: 0, isTextBox: true });
      slide.addText(c.text, { x: x + 0.25, y: y + 1.32, w: cw - 0.5, h: ch - 1.4, fontSize: cfs, color: C.text1,
        valign: "top", margin: 0, isTextBox: true });
    });
    const ty = TOP + ch + 0.25;
    const th = table(slide, s.table, M, ty, W - 2 * M, { firstCol: 3.6, font: 14, rowH: 0.38 });
    const fy = ty + th + 0.12, fh = BOTTOM - fy;
    const ffs = fitSize(s.footnote, W - 2 * M, fh, 11, 9, { em: EM_BODY * 1.04 }, `${CURRENT} — виноска`);
    slide.addText(s.footnote, { x: M, y: fy, w: W - 2 * M, h: fh, fontSize: ffs,
      color: C.accent6, valign: "top", margin: 0, isTextBox: true, italic: true });
  },
  chart(s) {
    const slide = newSlide(s);
    const avail = W - 2 * M;
    if (s.layout === "below") {
      const bulletsH = s.bullets.length ? 1.15 : 0;
      const maxH = BOTTOM - TOP - bulletsH - 0.25;
      if (s.side_image) {
        const r = image(slide, s.image, M, TOP, avail * 0.66, maxH, "chart main");
        image(slide, s.side_image, M + r.w + 0.25, TOP, avail - r.w - 0.25, maxH, "chart side");
      } else {
        const ar = s.image.w / s.image.h; const w = Math.min(avail, maxH * ar);
        image(slide, s.image, M + (avail - w) / 2, TOP, w, maxH, "chart");
      }
      numberedRow(slide, s.bullets, M, BOTTOM - bulletsH, avail, bulletsH);
    } else if (s.layout === "right") {
      const leftW = 7.7, maxH = BOTTOM - TOP;
      if (s.side_image) {
        const r = image(slide, s.image, M, TOP, leftW, maxH * 0.55, "chart main");
        image(slide, s.side_image, M, TOP + r.h + 0.15, leftW, maxH - r.h - 0.15, "chart side");
      } else {
        image(slide, s.image, M, TOP, leftW, maxH, "chart");
      }
      bulletsBox(slide, s.bullets, M + leftW + 0.35, TOP + 0.1, avail - leftW - 0.35, maxH - 0.1, 14);
    } else {
      const maxH = BOTTOM - TOP, ar = s.image.w / s.image.h, w = Math.min(avail, maxH * ar);
      image(slide, s.image, M + (avail - w) / 2, TOP, w, maxH, "chart");
    }
  },
  chart_table(s) {
    const slide = newSlide(s);
    if (s.layout === "stack") {
      // chart on top, table bottom-left, bullets bottom-right: the chart gets what the lower row leaves
      const avail = W - 2 * M, ar = s.image.w / s.image.h, tw = 7.3, bw = avail - tw - 0.35;
      const tOpts = { firstCol: 2.6, rowH: 0.32 };
      const tH = tableHeight(s.table, colWidths(s.table, tw, tOpts), 12, 0.32);
      const need = Math.max(tH, textHeight(s.bullets, 12.5, bw, BULLET));
      const ih = Math.max(2.1, Math.min(2.85, avail / ar, BOTTOM - TOP - 0.2 - need));
      const iw = ih * ar;
      image(slide, s.image, M + (avail - iw) / 2, TOP - 0.05, iw, ih, "chart");
      const y = TOP + ih + 0.15;
      const tfs = fitTable(s.table, tw, BOTTOM - y, 12, 10, tOpts);
      table(slide, s.table, M, y, tw, { ...tOpts, font: tfs });
      bulletsBox(slide, s.bullets, M + tw + 0.35, y + 0.02, bw, BOTTOM - y - 0.02, 13, 10.5);
      return;
    }
    const leftW = 6.9, maxH = BOTTOM - TOP;
    image(slide, s.image, M, TOP, leftW, maxH, "chart");
    const x = M + leftW + 0.35, w = W - M - x;
    const rowsH = table(slide, s.table, x, TOP, w, { firstCol: w * 0.3, font: 12, rowH: 0.36 });
    bulletsBox(slide, s.bullets, x, TOP + rowsH + 0.3, w, BOTTOM - TOP - rowsH - 0.3, 13);
  },
  table(s) {
    const slide = newSlide(s);
    const opts = { leftAll: true, rowH: s.table.rowH };
    const fs_ = fitTable(s.table, W - 2 * M, BOTTOM - TOP, s.table.font || 12, 9, opts);
    table(slide, s.table, M, TOP, W - 2 * M, { ...opts, font: fs_ });
  },
  process(s) {
    const slide = newSlide(s);
    const n = s.steps.length, gap = 0.45, bw = (W - 2 * M - gap * (n - 1)) / n, bh = 1.75, y = TOP + 0.1;
    s.steps.forEach((st, i) => {
      const x = M + i * (bw + gap);
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: bw, h: bh, rectRadius: 0.08, fill: { color: HEX.tint },
        line: { type: "none" }, objectName: `step${i + 1}` });
      slide.addText(`${i + 1}. ${st.head}`, { x: x + 0.2, y: y + 0.12, w: bw - 0.4, h: 0.55, bold: true,
        fontSize: fitSize(`${i + 1}. ${st.head}`, bw - 0.4, 0.55, 17, 13, { em: EM_HEAD }, `${CURRENT} — крок`),
        color: C.accent1, margin: 0, isTextBox: true, fontFace: THEME.headFontFace });
      slide.addText(st.text, { x: x + 0.2, y: y + 0.7, w: bw - 0.4, h: bh - 0.85, color: C.text1,
        fontSize: fitSize(st.text, bw - 0.4, bh - 0.85, 13, 10.5, {}, `${CURRENT} — крок ${i + 1}`),
        valign: "top", margin: 0, isTextBox: true });
      if (i < n - 1) slide.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.08, y: y + bh / 2 - 0.15, w: gap - 0.16, h: 0.3,
        fill: { color: HEX.gold }, line: { type: "none" }, objectName: `arrow${i + 1}` });
    });
    const sy = y + bh + 0.45, sw = (W - 2 * M - 0.6) / s.stats.length;
    s.stats.forEach((st, i) => {
      const x = M + i * (sw + 0.3);
      slide.addText(st.value, { x, y: sy, w: sw, h: 0.85, fontSize: 34, bold: true, color: HEX.gold, margin: 0,
        isTextBox: true, fontFace: THEME.headFontFace });
      slide.addText(st.label, { x, y: sy + 0.9, w: sw, h: 0.7, color: C.text1, valign: "top", margin: 0,
        fontSize: fitSize(st.label, sw, 0.7, 14, 10.5, {}, `${CURRENT} — показник`), isTextBox: true });
    });
    if (s.chips) {
      slide.addText("Що ми додали до шаблону НБУ", { x: M, y: BOTTOM - 1.45, w: 6, h: 0.32, fontSize: 13, bold: true,
        color: C.accent1, margin: 0, isTextBox: true });
      let cx = M, cy = BOTTOM - 1.05;
      s.chips.forEach((c, i) => {
        const cw = 0.085 * c.length + 0.4;
        if (cx + cw > W - M) { cx = M; cy += 0.5; }
        slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: cx, y: cy, w: cw, h: 0.4, rectRadius: 0.2,
          fill: { color: HEX.tint }, line: { color: HEX.teal, width: 0.75 }, objectName: `chip${i + 1}` });
        slide.addText(c, { x: cx, y: cy, w: cw, h: 0.4, fontSize: 12, color: C.accent1, align: "center",
          valign: "middle", margin: 0, isTextBox: true });
        cx += cw + 0.15;
      });
    }
  },
  matrix(s) {
    const slide = newSlide(s);
    const lx = M + 0.9, ty = TOP + 0.05, cw = (W - 2 * M - 0.9) / 3, rh = (BOTTOM - TOP - 0.6) / 3;
    const sev = { "Високий": 2, "Середній": 1, "Низький": 0 }, imp = { "Слабкий": 0, "Помірний": 1, "Сильний": 2 };
    const shades = ["F4F8F7", "E3EEEB", "CFE2DD", "B9D5CE", "A3C8BF"];
    s.rows.forEach((r, ri) => {
      slide.addText(r, { x: M, y: ty + ri * rh, w: 0.85, h: rh, fontSize: 12, bold: true, color: C.accent6, align: "center",
        valign: "middle", margin: 0, isTextBox: true });
      s.cols.forEach((c, ci) => {
        const x = lx + ci * cw, y = ty + ri * rh;
        slide.addShape(pres.shapes.RECTANGLE, { x: x + 0.04, y: y + 0.04, w: cw - 0.08, h: rh - 0.08,
          fill: { color: shades[sev[r] + imp[c]] }, line: { type: "none" }, objectName: `cell ${r}/${c}` });
        const cell = s.cells.find((q) => q.row === r && q.col === c);
        if (cell) {
          const txt = cell.items.map((it) => "▲ " + it.text);
          const mfs = fitSize(txt, cw - 0.36, rh - 0.24, 13, 10, { paraAfter: 4, em: EM_BODY * 1.06 }, `${CURRENT} — клітинка`);
          slide.addText(cell.items.map((it, k) => ({ text: (it.dir === "↑" ? "▲ " : "▼ ") + it.text, options: {
            color: it.dir === "↑" ? HEX.up : HEX.down, breakLine: k < cell.items.length - 1, paraSpaceAfter: 4 } })),
            { x: x + 0.18, y: y + 0.12, w: cw - 0.36, h: rh - 0.24, fontSize: mfs, valign: "middle", margin: 0,
              isTextBox: true, bold: true });
        }
      });
    });
    s.cols.forEach((c, ci) => slide.addText(c, { x: lx + ci * cw, y: ty + 3 * rh + 0.02, w: cw, h: 0.3, fontSize: 12,
      bold: true, color: C.accent6, align: "center", margin: 0, isTextBox: true }));
    slide.addText("Імовірність ↑   ·   Вплив на базовий сценарій →   ·   ▲ вища інфляція   ▼ нижча інфляція",
      { x: lx, y: ty + 3 * rh + 0.32, w: W - lx - M, h: 0.28, fontSize: 11, color: C.accent6, margin: 0, isTextBox: true });
  },
  reco(s) {
    const slide = newSlide(s);
    const bw = 3.4, bh = BOTTOM - TOP;
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y: TOP, w: bw, h: bh, rectRadius: 0.1, fill: { color: HEX.teal },
      line: { type: "none" }, objectName: "decision" });
    slide.addText("ОБЛІКОВА СТАВКА", { x: M + 0.3, y: TOP + 0.4, w: bw - 0.6, h: 0.35, fontSize: 13, bold: true,
      color: "CFE3DE", charSpacing: 1, margin: 0, isTextBox: true });
    slide.addText(s.big, { x: M + 0.3, y: TOP + 0.9, w: bw - 0.6, h: 1.4, fontSize: 66, bold: true, color: HEX.gold,
      fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    slide.addText(s.big_label, { x: M + 0.3, y: TOP + 2.35, w: bw - 0.6, h: 0.8, fontSize: 16, color: C.background1,
      margin: 0, isTextBox: true });
    const x = M + bw + 0.4, w = W - M - x;
    // each group gets a heading (0.4 in) and exactly the height its bullets need; one font size for all groups,
    // the largest at which the stack fits; leftover space is spread between the groups
    const HEAD = 0.38, GAP = 0.12, RB = { indent: BULLET.indent, paraAfter: 5 };   // tighter than other slides: 10 items
    const need = (fs_) => s.groups.map((g) => HEAD + textHeight(g.items, fs_, w, RB));
    let fs_ = 14;
    const room = bh - GAP * (s.groups.length - 1);
    while (fs_ > 11 && need(fs_).reduce((a, b) => a + b, 0) > room) fs_ -= 0.5;
    const hs = need(fs_), total = hs.reduce((a, b) => a + b, 0);
    if (process.env.DECK_DEBUG) console.log(`  [reco ${fs_}] ${CURRENT}: ${hs.map((v) => v.toFixed(2)).join(" / ")} з ${room.toFixed(2)}`);
    if (total > room + 0.01) OVERFLOW.push(`${CURRENT} — групи: потрібно ${total.toFixed(2)} in, є ${room.toFixed(2)} in`);
    const spare = Math.max(0, room - total) / s.groups.length;
    let y = TOP;
    s.groups.forEach((g, i) => {
      slide.addText(g.head, { x, y, w, h: 0.36, fontSize: 16, bold: true, color: C.accent1, margin: 0, isTextBox: true,
        fontFace: THEME.headFontFace });
      const gh = hs[i] - HEAD + spare;
      slide.addText(g.items.map((t, k) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: k < g.items.length - 1,
        paraSpaceAfter: 5 } })), { x, y: y + HEAD, w, h: gh, fontSize: fs_, color: C.text1, valign: "top", margin: 0,
        isTextBox: true, objectName: "bullets" });
      y += HEAD + gh + GAP;
    });
  },
  bullets2(s) {
    const slide = newSlide(s);
    const n = s.groups.length, gap = 0.3, cw = (W - 2 * M - gap * (n - 1)) / n, ch = s.quote ? 3.55 : BOTTOM - TOP;
    if (s.quote) {
      slide.addText(s.quote, { x: M, y: TOP + ch + 0.3, w: W - 2 * M, h: BOTTOM - TOP - ch - 0.3, fontSize: 14,
        italic: true, color: C.accent1, valign: "middle", margin: [6, 12, 6, 12], isTextBox: true,
        fill: { color: "FFFFFF" }, line: { color: HEX.gold, width: 1.25 }, objectName: "press release" });
    }
    s.groups.forEach((g, i) => {
      const x = M + i * (cw + gap);
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: TOP, w: cw, h: ch, rectRadius: 0.08, fill: { color: HEX.tint },
        line: { type: "none" }, objectName: `card${i + 1}` });
      slide.addShape(pres.shapes.OVAL, { x: x + 0.25, y: TOP + 0.25, w: 0.5, h: 0.5, fill: { color: HEX.gold },
        line: { type: "none" }, objectName: `badge${i + 1}` });
      slide.addText(String(i + 1), { x: x + 0.25, y: TOP + 0.25, w: 0.5, h: 0.5, fontSize: 18, bold: true,
        color: C.background1, align: "center", valign: "middle", margin: 0, isTextBox: true });
      slide.addText(g.head, { x: x + 0.9, y: TOP + 0.25, w: cw - 1.1, h: 0.5, bold: true, color: C.accent1,
        fontSize: fitSize(g.head, cw - 1.1, 0.5, 17, 13, { em: EM_HEAD }, `${CURRENT} — заголовок картки`),
        valign: "middle", margin: 0, isTextBox: true, fontFace: THEME.headFontFace });
      bulletsBox(slide, g.items, x + 0.3, TOP + 1.0, cw - 0.55, ch - 1.2, 14);
    });
  },
  summary_end(s) {
    CURRENT = s.title;
    const slide = pres.addSlide({ masterName: "DARK", sectionTitle: s.section });
    slide.addText(s.title, { x: 0.8, y: 0.7, w: 11.7, h: 0.9, fontSize: 36, bold: true, color: C.background1,
      fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    s.items.forEach((t, i) => {
      const y = 1.95 + i * 1.15;
      slide.addShape(pres.shapes.OVAL, { x: 0.8, y, w: 0.62, h: 0.62, fill: { color: HEX.gold }, line: { type: "none" },
        objectName: `n${i + 1}` });
      slide.addText(String(i + 1), { x: 0.8, y, w: 0.62, h: 0.62, fontSize: 20, bold: true, color: HEX.teal,
        align: "center", valign: "middle", margin: 0, isTextBox: true });
      slide.addText(t, { x: 1.7, y: y - 0.08, w: 10.8, h: 0.8, color: C.background1, valign: "middle",
        fontSize: fitSize(t, 10.8, 0.8, 20, 15, {}, `${CURRENT} — пункт ${i + 1}`),
        margin: 0, isTextBox: true });
    });
    if (s.notes) slide.addNotes(s.notes);
  },
  equations(s) {
    const slide = newSlide(s);
    let y = TOP;
    s.eqs.forEach(([name, eq], i) => {
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: M, y, w: W - 2 * M, h: 0.82, rectRadius: 0.06,
        fill: { color: i % 2 ? "FFFFFF" : HEX.tint }, line: { color: HEX.grid, width: 0.5 }, objectName: `eq${i + 1}` });
      slide.addText(name, { x: M + 0.25, y, w: 3.3, h: 0.82, fontSize: 14, bold: true, color: C.accent1, valign: "middle",
        margin: 0, isTextBox: true });
      slide.addText(eq, { x: M + 3.6, y, w: W - 2 * M - 3.8, h: 0.82, color: C.text1, valign: "middle",
        fontSize: fitSize(eq, W - 2 * M - 3.8, 0.8, 16, 12, { em: 0.45 }, `${CURRENT} — рівняння ${i + 1}`),
        margin: 0, isTextBox: true, fontFace: "Cambria Math" });
      y += 0.95;
    });
    numberedRow(slide, s.bullets, M, y + 0.25, W - 2 * M, BOTTOM - y - 0.25);
  },
};

// ------------------------------------------------------------------ build
const added = new Set();
for (const s of DATA.slides) {
  const sec = s.section || "Вступ";
  if (!added.has(sec)) { pres.addSection({ title: sec }); added.add(sec); }
  if (!R[s.type]) throw new Error("Unknown slide type: " + s.type);
  R[s.type](s);
}
if (OVERFLOW.length) {
  console.warn("Текст не вміщається навіть на мінімальному кеглі (скоротіть у deck/content.py):");
  OVERFLOW.forEach((o) => console.warn("  - " + o));
  if (process.env.DECK_STRICT) process.exit(1);
}
fs.mkdirSync(OUT_DIR, { recursive: true });
pres.writeFile({ fileName: OUT }).then(async (f) => {
  if (APPLY_THEME && fs.existsSync(APPLY_THEME)) {
    const { applyTheme } = require(APPLY_THEME);
    await applyTheme(OUT, THEME);
  } else {
    console.warn("deck/apply_theme.js не знайдено — схемні кольори будуть стандартними для Office");
  }
  console.log("Збережено:", f);
});

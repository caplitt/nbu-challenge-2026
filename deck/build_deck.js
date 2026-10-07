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

// ------------------------------------------------------------------ helpers
function image(slide, im, x, y, maxW, maxH, name) {
  const ar = im.w / im.h;
  let w = maxW, h = maxW / ar;
  if (h > maxH) { h = maxH; w = maxH * ar; }
  slide.addImage({ path: im.path, x, y, w, h, objectName: name || "chart" });
  return { x, y, w, h };
}
function bulletsBox(slide, items, x, y, w, h, size = 14) {
  if (!items || !items.length) return;
  slide.addText(items.map((t, i) => ({ text: t, options: { bullet: { indent: 14 }, breakLine: i < items.length - 1,
    paraSpaceAfter: 8 } })), { x, y, w, h, fontSize: size, color: C.text1, valign: "top", margin: 0, isTextBox: true,
    objectName: "bullets" });
}
function numberedRow(slide, items, x, y, w, h) {
  const n = items.length, gap = 0.3, cw = (w - gap * (n - 1)) / n;
  items.forEach((t, i) => {
    const cx = x + i * (cw + gap);
    slide.addShape(pres.shapes.OVAL, { x: cx, y: y + 0.02, w: 0.34, h: 0.34, fill: { color: HEX.gold }, line: { type: "none" },
      objectName: `num${i + 1}` });
    slide.addText(String(i + 1), { x: cx, y: y + 0.02, w: 0.34, h: 0.34, fontSize: 12, bold: true, color: C.background1,
      align: "center", valign: "middle", margin: 0, isTextBox: true });
    slide.addText(t, { x: cx + 0.45, y, w: cw - 0.45, h, fontSize: 13, color: C.text1, valign: "top", margin: 0,
      isTextBox: true, objectName: `point${i + 1}` });
  });
}
function table(slide, t, x, y, w, opts = {}) {
  const fs_ = t.font || opts.font || 12;
  const header = t.header.map((h) => ({ text: h, options: { bold: true, color: C.background1, fill: { color: HEX.teal },
    fontSize: fs_, valign: "middle" } }));
  const rows = t.rows.map((r, ri) => r.map((c, ci) => ({ text: String(c), options: {
    fontSize: fs_, color: C.text1, fill: { color: ri % 2 ? HEX.tint : "FFFFFF" }, bold: ci === 0 || String(c).includes("★"),
    align: ci === 0 ? "left" : (opts.leftAll ? "left" : "center"), valign: "middle" } })));
  const colW = t.colw || (() => { const first = opts.firstCol || Math.min(3.2, w * 0.32);
    const rest = (w - first) / (t.header.length - 1); return [first, ...Array(t.header.length - 1).fill(rest)]; })();
  const rh = t.rowH || opts.rowH;
  const extra = rh ? { rowH: rh } : {};
  slide.addTable([header, ...rows], { x, y, w, colW, border: { type: "solid", pt: 0.5, color: HEX.grid },
    margin: [3, 5, 3, 5], autoPage: false, objectName: "table", ...extra });
}
function newSlide(s) {
  const master = s.section ? "CONTENT_" + s.section : "CONTENT_intro";
  const slide = pres.addSlide({ masterName: master, sectionTitle: s.section || "Вступ" });
  slide.addText(s.title, { placeholder: "title" });
  if (s.notes) slide.addNotes(s.notes);
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
    const n = s.cards.length, gap = 0.3, cw = (W - 2 * M - gap * (n - 1)) / n, ch = 2.35;
    s.cards.forEach((c, i) => {
      const x = M + i * (cw + gap), y = TOP;
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: cw, h: ch, rectRadius: 0.08, fill: { color: HEX.tint },
        line: { type: "none" }, objectName: `card${i + 1}` });
      slide.addText(c.label.toUpperCase(), { x: x + 0.25, y: y + 0.18, w: cw - 0.5, h: 0.3, fontSize: 11, bold: true,
        color: C.accent6, charSpacing: 1, margin: 0, isTextBox: true });
      slide.addText([{ text: c.value, options: { fontSize: 40, bold: true, color: C.accent1, fontFace: THEME.headFontFace } },
        { text: "  " + c.delta, options: { fontSize: 15, bold: true, color: HEX.gold } }],
        { x: x + 0.25, y: y + 0.5, w: cw - 0.5, h: 0.8, valign: "middle", margin: 0, isTextBox: true });
      slide.addText(c.text, { x: x + 0.25, y: y + 1.35, w: cw - 0.5, h: 0.9, fontSize: 13, color: C.text1, valign: "top",
        margin: 0, isTextBox: true });
    });
    const ty = TOP + ch + 0.35;
    table(slide, s.table, M, ty, W - 2 * M, { firstCol: 3.6, font: 15, rowH: 0.42 });
    slide.addText(s.footnote, { x: M, y: ty + 0.42 * (s.table.rows.length + 1) + 0.2, w: W - 2 * M, h: 0.55, fontSize: 11,
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
      const avail = W - 2 * M, ar = s.image.w / s.image.h, ih = Math.min(2.85, avail / ar);
      const iw = ih * ar;
      image(slide, s.image, M + (avail - iw) / 2, TOP - 0.05, iw, ih, "chart");
      const y = TOP + ih + 0.15, tw = 7.7;
      table(slide, s.table, M, y, tw, { firstCol: 2.9, font: 12, rowH: 0.34 });
      bulletsBox(slide, s.bullets, M + tw + 0.35, y + 0.05, avail - tw - 0.35, BOTTOM - y - 0.05, 13);
      return;
    }
    const leftW = 6.9, maxH = BOTTOM - TOP;
    image(slide, s.image, M, TOP, leftW, maxH, "chart");
    const x = M + leftW + 0.35, w = W - M - x;
    table(slide, s.table, x, TOP, w, { firstCol: w * 0.3, font: 12, rowH: 0.36 });
    const rowsH = 0.36 * (s.table.rows.length + 1) + 0.25;
    bulletsBox(slide, s.bullets, x, TOP + rowsH + 0.2, w, BOTTOM - TOP - rowsH - 0.2, 13);
  },
  table(s) {
    const slide = newSlide(s);
    table(slide, s.table, M, TOP, W - 2 * M, { font: s.table.font || 12, leftAll: true });
  },
  process(s) {
    const slide = newSlide(s);
    const n = s.steps.length, gap = 0.45, bw = (W - 2 * M - gap * (n - 1)) / n, bh = 1.75, y = TOP + 0.1;
    s.steps.forEach((st, i) => {
      const x = M + i * (bw + gap);
      slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: bw, h: bh, rectRadius: 0.08, fill: { color: HEX.tint },
        line: { type: "none" }, objectName: `step${i + 1}` });
      slide.addText(`${i + 1}. ${st.head}`, { x: x + 0.2, y: y + 0.18, w: bw - 0.4, h: 0.45, fontSize: 17, bold: true,
        color: C.accent1, margin: 0, isTextBox: true, fontFace: THEME.headFontFace });
      slide.addText(st.text, { x: x + 0.2, y: y + 0.7, w: bw - 0.4, h: bh - 0.85, fontSize: 13, color: C.text1,
        valign: "top", margin: 0, isTextBox: true });
      if (i < n - 1) slide.addShape(pres.shapes.RIGHT_ARROW, { x: x + bw + 0.08, y: y + bh / 2 - 0.15, w: gap - 0.16, h: 0.3,
        fill: { color: HEX.gold }, line: { type: "none" }, objectName: `arrow${i + 1}` });
    });
    const sy = y + bh + 0.45, sw = (W - 2 * M - 0.6) / s.stats.length;
    s.stats.forEach((st, i) => {
      const x = M + i * (sw + 0.3);
      slide.addText(st.value, { x, y: sy, w: sw, h: 0.85, fontSize: 34, bold: true, color: HEX.gold, margin: 0,
        isTextBox: true, fontFace: THEME.headFontFace });
      slide.addText(st.label, { x, y: sy + 0.9, w: sw, h: 0.7, fontSize: 14, color: C.text1, valign: "top", margin: 0,
        isTextBox: true });
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
          slide.addText(cell.items.map((it, k) => ({ text: (it.dir === "↑" ? "▲ " : "▼ ") + it.text, options: {
            color: it.dir === "↑" ? HEX.up : HEX.down, breakLine: k < cell.items.length - 1, paraSpaceAfter: 4 } })),
            { x: x + 0.18, y: y + 0.12, w: cw - 0.36, h: rh - 0.24, fontSize: 13, valign: "middle", margin: 0,
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
    let y = TOP;
    const lines = s.groups.map((g) => g.items.reduce((a, t) => a + Math.ceil(t.length / 105), 0));
    const unit = (bh - 0.55 * s.groups.length) / lines.reduce((a, b) => a + b, 0);
    s.groups.forEach((g, i) => {
      const gh = 0.5 + lines[i] * unit;
      slide.addText(g.head, { x, y, w, h: 0.38, fontSize: 16, bold: true, color: C.accent1, margin: 0, isTextBox: true,
        fontFace: THEME.headFontFace });
      bulletsBox(slide, g.items, x, y + 0.42, w, gh - 0.42, 14);
      y += gh + 0.05;
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
      slide.addText(g.head, { x: x + 0.9, y: TOP + 0.25, w: cw - 1.1, h: 0.5, fontSize: 17, bold: true, color: C.accent1,
        valign: "middle", margin: 0, isTextBox: true, fontFace: THEME.headFontFace });
      bulletsBox(slide, g.items, x + 0.3, TOP + 1.0, cw - 0.55, ch - 1.2, 14);
    });
  },
  summary_end(s) {
    const slide = pres.addSlide({ masterName: "DARK", sectionTitle: s.section });
    slide.addText(s.title, { x: 0.8, y: 0.7, w: 11.7, h: 0.9, fontSize: 36, bold: true, color: C.background1,
      fontFace: THEME.headFontFace, margin: 0, isTextBox: true });
    s.items.forEach((t, i) => {
      const y = 1.95 + i * 1.15;
      slide.addShape(pres.shapes.OVAL, { x: 0.8, y, w: 0.62, h: 0.62, fill: { color: HEX.gold }, line: { type: "none" },
        objectName: `n${i + 1}` });
      slide.addText(String(i + 1), { x: 0.8, y, w: 0.62, h: 0.62, fontSize: 20, bold: true, color: HEX.teal,
        align: "center", valign: "middle", margin: 0, isTextBox: true });
      slide.addText(t, { x: 1.7, y: y - 0.08, w: 10.8, h: 0.8, fontSize: 20, color: C.background1, valign: "middle",
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
      slide.addText(eq, { x: M + 3.6, y, w: W - 2 * M - 3.8, h: 0.82, fontSize: 16, color: C.text1, valign: "middle",
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

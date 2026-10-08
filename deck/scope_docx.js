// docs/scope_of_work.md -> docs/scope_of_work.docx (Word): headings, paragraphs, lists, tables, clickable links.
// Run from the repo root:  node deck/scope_docx.js   (NODE_PATH=deck/node_modules when run from elsewhere)
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ExternalHyperlink, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, HeadingLevel, AlignmentType, LevelFormat, Footer, PageNumber, TableLayoutType,
} = require("docx");

const ROOT = path.resolve(__dirname, "..");
const SRC = path.join(ROOT, "docs", "scope_of_work.md");
const OUT = path.join(ROOT, "docs", "scope_of_work.docx");

const TEAL = "0E3B43", GOLD = "A87300", TINT = "EAF1EF", GRID = "C9D6D3", LINK = "1F63B5", MUTED = "5F6B6D";
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1021;           // A4, 1.8 cm margins
const CONTENT_W = PAGE_W - 2 * MARGIN;
const BODY = 20, TABLE = 17;                                     // half-points: 10 pt, 8.5 pt

// ---------------------------------------------------------------- inline markdown -> runs
function runs(text, size, extra = {}) {
  const out = [];
  const re = /\[([^\]]+)\]\(([^)\s]+)\)|\*\*([^*]+)\*\*|`([^`]+)`/g;
  let last = 0, m;
  const plain = (t) => t && out.push(new TextRun({ text: t, size, ...extra }));
  while ((m = re.exec(text))) {
    plain(text.slice(last, m.index));
    if (m[1] !== undefined) {
      const label = m[1].replace(/`/g, "");
      if (/^https?:\/\//.test(m[2])) {
        out.push(new ExternalHyperlink({ link: m[2], children: [new TextRun({ text: label, size, color: LINK,
          underline: {}, ...extra })] }));
      } else {   // repository-relative link: the repo is private, so show the path as text
        out.push(new TextRun({ text: `docs/${m[2]}`, size, font: "Consolas", ...extra }));
      }
    } else if (m[3] !== undefined) {
      out.push(new TextRun({ text: m[3], size, bold: true, ...extra }));
    } else {
      out.push(new TextRun({ text: m[4], size: size - 2, font: "Consolas", ...extra }));
    }
    last = re.lastIndex;
  }
  plain(text.slice(last));
  return out;
}

// ---------------------------------------------------------------- tables
const border = { style: BorderStyle.SINGLE, size: 4, color: GRID };
const borders = { top: border, bottom: border, left: border, right: border };

function splitRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
}
function columnWidths(rows) {
  const n = rows[0].length;
  const visible = (t) => t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/[`*]/g, "");
  const w = [];
  for (let j = 0; j < n; j++) {
    const lens = rows.map((r) => visible(r[j] || "").length);
    const mean = lens.reduce((a, b) => a + b, 0) / lens.length;
    w.push(Math.min(Math.max(mean, 9), 60));
  }
  const total = w.reduce((a, b) => a + b, 0);
  const cols = w.map((x) => Math.floor((x / total) * CONTENT_W));
  cols[n - 1] += CONTENT_W - cols.reduce((a, b) => a + b, 0);   // exact sum
  return cols;
}
function table(lines) {
  const rows = lines.filter((l, i) => !(i === 1 && /^\|[\s:|-]+\|$/.test(l.trim()))).map(splitRow);
  const cols = columnWidths(rows);
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: cols,
    layout: TableLayoutType.FIXED,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      cantSplit: true,
      children: r.map((c, ci) => new TableCell({
        width: { size: cols[ci], type: WidthType.DXA },
        borders,
        shading: { type: ShadingType.CLEAR, color: "auto",
          fill: ri === 0 ? TEAL : (ri % 2 === 0 ? TINT : "FFFFFF") },
        margins: { top: 50, bottom: 50, left: 90, right: 90 },
        children: [new Paragraph({ spacing: { before: 0, after: 0, line: 252 },
          children: ri === 0 ? runs(c, TABLE, { bold: true, color: "FFFFFF" })
            : runs(c, TABLE, ci === 0 ? { bold: true } : {}) })],
      })),
    })),
  });
}

// ---------------------------------------------------------------- document body
const lines = fs.readFileSync(SRC, "utf8").replace(/\r/g, "").split("\n");
const body = [];
let i = 0, numberedList = 0;
while (i < lines.length) {
  const line = lines[i];
  if (!line.trim()) { i++; continue; }
  if (line.startsWith("|")) {
    const block = [];
    while (i < lines.length && lines[i].startsWith("|")) block.push(lines[i++]);
    body.push(table(block));
    body.push(new Paragraph({ spacing: { before: 0, after: 80 }, children: [] }));
    continue;
  }
  if (line.startsWith("# ")) {
    body.push(new Paragraph({ heading: HeadingLevel.TITLE, children: runs(line.slice(2), 40, { color: TEAL, bold: true,
      font: "Cambria" }) }));
  } else if (line.startsWith("## ")) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: runs(line.slice(3), 28, { color: TEAL,
      bold: true, font: "Cambria" }) }));
  } else if (line.startsWith("### ")) {
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: runs(line.slice(4), 23, { color: TEAL,
      bold: true, font: "Cambria" }) }));
  } else if (/^- /.test(line)) {
    body.push(new Paragraph({ numbering: { reference: "bullets", level: 0 }, spacing: { after: 40 },
      children: runs(line.slice(2), BODY) }));
  } else if (/^\d+\. /.test(line)) {
    if (!/^\d+\. /.test(lines[i - 1] || "")) numberedList++;
    body.push(new Paragraph({ numbering: { reference: "steps", level: 0, instance: numberedList }, spacing: { after: 20 },
      children: runs(line.replace(/^\d+\. /, ""), BODY) }));
  } else {
    body.push(new Paragraph({ spacing: { after: 120 }, children: runs(line, BODY) }));
  }
  i++;
}

const doc = new Document({
  creator: "NBU University Challenge 2026",
  title: "Обсяг роботи: дані, модель, прогноз, перевірка, презентація",
  styles: {
    default: { document: { run: { font: "Calibri", size: BODY, color: "1B2326" } } },
    paragraphStyles: [
      { id: "Title", name: "Title", basedOn: "Normal", run: { font: "Cambria", size: 40, bold: true, color: TEAL },
        paragraph: { spacing: { after: 160 } } },
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Cambria", size: 28, bold: true, color: TEAL },
        paragraph: { spacing: { before: 280, after: 100 }, keepNext: true, outlineLevel: 0,
          border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: GOLD, space: 2 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: "Cambria", size: 23, bold: true, color: TEAL },
        paragraph: { spacing: { before: 200, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [
    { reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    { reference: "steps", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 300 } } } }] },
  ] },
  sections: [{
    properties: { page: { size: { width: PAGE_W, height: PAGE_H },
      margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [
      new TextRun({ text: "NBU University Challenge 2026 · Обсяг роботи · ", size: 16, color: MUTED }),
      new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MUTED }),
      new TextRun({ text: " / ", size: 16, color: MUTED }),
      new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: MUTED }),
    ] })] }) },
    children: body,
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("Збережено:", OUT);
});

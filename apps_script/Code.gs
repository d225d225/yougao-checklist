/**
 * 永平高中優質化・子計畫自主管理檢核表 — Google Apps Script 橋接
 *
 * 部署方式：網頁應用程式，執行身分「我」，存取權「任何人」。
 * 不需要啟用進階服務，也不需要設定指令碼屬性。
 */

// 與 Streamlit secrets 的 GAS_SECRET 相同
const SECRET = '請改成與 GAS_SECRET 相同的一串亂碼';

const ROOT_FOLDER_ID = '1mjAB9-dhPu4ZuljboSozfwe7HH2s_IAa';      // 優高檢核專區
const REFERENCE_FOLDER_ID = '16Gr5GnpgbZIcZ_wUxKjUYGD6CkhbDBlE'; // reference
const TEMPLATE_DOC_ID = '1VKJ6VfCo6Y78yivZfnXHzO6xRnny08GweV1wuh_2_QM'; // 空白檢核表
const RAW_FOLDER_NAME = '原始資料';
const CONFIG_FILE_NAME = '_config.json';

// 模板主表格：各列「邏輯儲存格」（合併後）對應的格線起始欄（共 15 欄）。
// 用來同時支援 DocumentApp 回傳「合併後格數」或「完整格線格數」兩種情況。
const GRID_STARTS = {
  r0: [0, 1, 7, 11],                    // 類別｜勾選｜子計畫名稱｜值
  money: [0, 1, 4, 5, 6, 7, 12],        // 經費 / 執行率
  wide: [0, 1],                         // 經費規畫、亮點、困難、PLC、總體評估
  act: [0, 1, 2, 5, 7, 9, 10, 13, 14],  // 活動列：合併欄｜日期｜項目｜摘要｜★1..5
  r22: [0, 1, 7],
  r23: [0, 1, 3, 7, 8],
  pair: [0, 1, 7],                      // 檢討修正、相片、說明
};
const ROW = {
  category: 0, money: 1, rate: 2, budget: 3,
  actFirst: 6, actLast: 21,
  qual: 23, review: 25, highlight: 26, problem: 27, plc: 28,
  photoFirst: 29, photoPairs: 16, overall: 61,
};
const BLACK = '#000000'; // 文件內所有文字一律黑色
const PHOTO_MAX_W = 190; // pt，約為半欄寬
const PHOTO_MAX_H = 150;

/* ---------------- Web App 進入點 ---------------- */

function doPost(e) {
  try {
    const p = JSON.parse(e.postData.contents);
    if (p.secret !== SECRET) return json_({ ok: false, error: 'unauthorized' });
    const fn = ACTIONS[p.action];
    if (!fn) return json_({ ok: false, error: 'unknown action: ' + p.action });
    return json_({ ok: true, result: fn(p) });
  } catch (err) {
    return json_({ ok: false, error: String(err && err.stack || err) });
  }
}

function doGet() {
  return json_({ ok: true, result: 'yougao-checklist bridge alive' });
}

const ACTIONS = {
  ping: () => 'pong',
  getReference: getReference_,
  getFile: getFile_,
  ensureFolder: (p) => ensureSubplanFolder_(p.subplan).getId(),
  readJson: readJson_,
  writeJson: writeJson_,
  uploadFile: uploadFile_,
  buildDoc: buildDoc_,
  inspectTemplate: inspectTemplate_,
};

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

/* ---------------- 資料夾與檔案 ---------------- */

function ensureSubplanFolder_(subplan) {
  if (!subplan || subplan === 'reference') throw new Error('invalid subplan: ' + subplan);
  const root = DriveApp.getFolderById(ROOT_FOLDER_ID);
  return childFolder_(root, subplan, true);
}

function childFolder_(parent, name, create) {
  const it = parent.getFoldersByName(name);
  if (it.hasNext()) return it.next();
  return create ? parent.createFolder(name) : null;
}

function findFile_(folder, name) {
  const it = folder.getFilesByName(name);
  while (it.hasNext()) {
    const f = it.next();
    if (!f.isTrashed()) return f;
  }
  return null;
}

/** subplan 為空時，讀寫根資料夾（存放 _config.json）。 */
function targetFolder_(subplan) {
  return subplan ? ensureSubplanFolder_(subplan) : DriveApp.getFolderById(ROOT_FOLDER_ID);
}

function readJson_(p) {
  const f = findFile_(targetFolder_(p.subplan), p.name);
  return f ? JSON.parse(f.getBlob().getDataAsString('UTF-8')) : null;
}

function writeJson_(p) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const folder = targetFolder_(p.subplan);
    const text = JSON.stringify(p.content, null, 1);
    const f = findFile_(folder, p.name);
    if (f) f.setContent(text);
    else folder.createFile(p.name, text, 'application/json');
    return true;
  } finally {
    lock.releaseLock();
  }
}

function uploadFile_(p) {
  const folder = ensureSubplanFolder_(p.subplan);
  let target = childFolder_(folder, RAW_FOLDER_NAME, true);
  if (p.subdir) target = childFolder_(target, p.subdir, true);
  const blob = Utilities.newBlob(Utilities.base64Decode(p.base64), p.mimeType, p.name);
  const f = target.createFile(blob);
  return { id: f.getId(), url: f.getUrl() };
}

function getReference_() {
  const out = [];
  const it = DriveApp.getFolderById(REFERENCE_FOLDER_ID).getFiles();
  while (it.hasNext()) {
    const f = it.next();
    out.push({ id: f.getId(), name: f.getName(), mimeType: f.getMimeType(), size: f.getSize() });
  }
  return out;
}

function getFile_(p) {
  const f = DriveApp.getFileById(p.fileId);
  return { name: f.getName(), mimeType: f.getMimeType(), base64: Utilities.base64Encode(f.getBlob().getBytes()) };
}

/* ---------------- 模板檢查（開發用） ---------------- */

function inspectTemplate_() {
  const doc = DocumentApp.openById(TEMPLATE_DOC_ID);
  const table = doc.getBody().getTables()[0];
  const rows = [];
  for (let r = 0; r < table.getNumRows(); r++) {
    const row = table.getRow(r);
    const cells = [];
    for (let c = 0; c < row.getNumCells(); c++) {
      const cell = row.getCell(c);
      cells.push({ text: cell.getText().slice(0, 12), colSpan: safe_(() => cell.getColSpan()), rowSpan: safe_(() => cell.getRowSpan()) });
    }
    rows.push(cells);
  }
  return { numRows: table.getNumRows(), rows: rows, check: verifyLayout_(table) };
}

function safe_(fn) { try { return fn(); } catch (e) { return null; } }

/* 用 Logger 在編輯器內測試：執行 testInspect 後查看執行紀錄 */
function testInspect() { Logger.log(JSON.stringify(inspectTemplate_(), null, 1)); }

/* ---------------- 儲存格定位 ---------------- */

/**
 * 回傳某列第 logical 個「合併後」儲存格。
 * DocumentApp 對合併儲存格的回傳方式不一，這裡依實際格數判斷：
 *  - 格數 = 合併後格數 → 直接用 logical 索引
 *  - 格數 = 15（完整格線）→ 用 GRID_STARTS 換算
 *  - 其他 → 跳過 colSpan 為 0 的被合併格
 */
function cellAt_(table, r, logical, gridStarts) {
  const row = table.getRow(r);
  const n = row.getNumCells();
  if (n === gridStarts.length) return row.getCell(logical);
  if (n === 15) return row.getCell(gridStarts[logical]);
  let k = -1;
  for (let c = 0; c < n; c++) {
    const cell = row.getCell(c);
    const span = safe_(() => cell.getColSpan());
    if (span === 0) continue;
    k++;
    if (k === logical) return cell;
  }
  throw new Error('找不到儲存格 row ' + r + ' logical ' + logical + '（格數 ' + n + '）');
}

function verifyLayout_(table) {
  const checks = [
    [ROW.category, 2, GRID_STARTS.r0, '子計畫名稱'],
    [5, 1, GRID_STARTS.act, '日期'],
    [22, 1, GRID_STARTS.r22, '質化成效'],
    [24, 1, GRID_STARTS.pair, '檢討'],
    [ROW.photoFirst, 0, GRID_STARTS.pair, '相片或圖檔'],
    [ROW.overall, 0, GRID_STARTS.wide, '總體評估'],
  ];
  const errors = [];
  checks.forEach(([r, i, g, want]) => {
    try {
      const got = cellAt_(table, r, i, g).getText().replace(/\s/g, '');
      if (got.indexOf(want) < 0) errors.push('列' + r + '格' + i + ' 應為「' + want + '」實為「' + got + '」');
    } catch (e) { errors.push(String(e)); }
  });
  return errors;
}

/* ---------------- 產生 Google 文件 ---------------- */

function docName_(d) {
  return d.year + '_(' + d.subplan + ')永平高中優質化計畫自主管理檢核表';
}

function buildDoc_(p) {
  const d = p.data;
  const lock = LockService.getScriptLock();
  lock.waitLock(60000);
  try {
    const folder = ensureSubplanFolder_(d.subplan);
    const name = docName_(d);
    let file = (d.doc && d.doc.id) ? safe_(() => DriveApp.getFileById(d.doc.id)) : null;
    if (file && file.isTrashed()) file = null;
    if (!file) file = findFile_(folder, name);
    let docId;
    if (!file) {
      docId = DriveApp.getFileById(TEMPLATE_DOC_ID).makeCopy(name, folder).getId();
    } else {
      docId = file.getId();
      if (file.getName() !== name) file.setName(name);
      resetFromTemplate_(docId);
    }
    const doc = DocumentApp.openById(docId);
    fill_(doc, d);
    doc.saveAndClose();
    return { id: docId, url: 'https://docs.google.com/document/d/' + docId + '/edit' };
  } finally {
    lock.releaseLock();
  }
}

/** 把文件內容換回模板，文件 ID 不變。 */
function resetFromTemplate_(docId) {
  const tplBody = DocumentApp.openById(TEMPLATE_DOC_ID).getBody();
  const doc = DocumentApp.openById(docId);
  const body = doc.getBody();
  body.appendParagraph(''); // 先加一個暫存段落，才能刪除其他所有內容
  while (body.getNumChildren() > 1) body.getChild(0).removeFromParent();
  for (let i = 0; i < tplBody.getNumChildren(); i++) {
    const el = tplBody.getChild(i).copy();
    switch (el.getType()) {
      case DocumentApp.ElementType.PARAGRAPH: body.appendParagraph(el); break;
      case DocumentApp.ElementType.TABLE: body.appendTable(el); break;
      case DocumentApp.ElementType.LIST_ITEM: body.appendListItem(el); break;
      default: break;
    }
  }
  body.getChild(0).removeFromParent(); // 移除暫存段落
  doc.saveAndClose();
}

function setCell_(cell, text) {
  const lines = String(text == null ? '' : text).split('\n');
  // 模板的格子裡可能有清單項目（「1.」「-」），一律換成一般段落
  // 注意：Google 文件不允許插入完全空白的段落，所以空行一律用一個空白字元代替
  let first = cell.getChild(0);
  if (first.getType() !== DocumentApp.ElementType.PARAGRAPH) {
    first = cell.insertParagraph(0, lines[0] || ' ');
  }
  while (cell.getNumChildren() > 1) cell.getChild(cell.getNumChildren() - 1).removeFromParent();
  const para = first.asParagraph();
  const t0 = para.editAsText();
  const hasText = t0.getText().length > 0;
  const size = hasText ? t0.getFontSize(0) : null;
  const family = hasText ? t0.getFontFamily(0) : null;
  para.setText(lines[0] || ' ');
  for (let i = 1; i < lines.length; i++) cell.appendParagraph(lines[i] || ' ');
  // 整格統一：黑色、不粗體、同字級同字型
  for (let i = 0; i < cell.getNumChildren(); i++) {
    const t = cell.getChild(i).editAsText();
    t.setForegroundColor(BLACK).setBold(false);
    if (size) t.setFontSize(size);
    if (family) t.setFontFamily(family);
  }
}

function putImage_(cell, fileId) {
  setCell_(cell, '');
  const blob = DriveApp.getFileById(fileId).getBlob();
  const para = cell.getChild(0).asParagraph();
  para.setAlignment(DocumentApp.HorizontalAlignment.CENTER);
  const img = para.appendInlineImage(blob);
  const w = img.getWidth(), h = img.getHeight();
  const scale = Math.min(PHOTO_MAX_W / w, PHOTO_MAX_H / h, 1);
  img.setWidth(Math.round(w * scale)).setHeight(Math.round(h * scale));
}

/** 把 label 前面最近的「□」換成「■」（不用正規表達式，避免全形空白、不換行空白比對失敗）。 */
function tick_(cell, label) {
  const text = cell.editAsText();
  const s = text.getText();
  const at = s.indexOf(label);
  if (at < 0) return;
  for (let j = at - 1; j >= Math.max(0, at - 6); j--) {
    if (s.charAt(j) === '□') {
      text.deleteText(j, j);
      text.insertText(j, '■');
      return;
    }
  }
}

function fill_(doc, d) {
  const body = doc.getBody();
  const s = d.sheet; // 由 Streamlit 端整理好的填表內容

  // 表格上方段落
  body.replaceText('永平高中學年度', '永平高中' + d.year + '學年度');
  const paras = body.getParagraphs();
  for (let i = 0; i < paras.length; i++) {
    if (paras[i].getText().indexOf('執行月份') === 0) {
      paras[i].setText('執行月份：' + s.months + '　　　　　填表日期：' + s.fillDate);
      break;
    }
  }

  const t = body.getTables()[0];
  const errs = verifyLayout_(t);
  if (errs.length) throw new Error('模板結構與預期不符：' + errs.join('；'));

  // 類別、子計畫名稱
  if (s.category) tick_(cellAt_(t, ROW.category, 1, GRID_STARTS.r0), s.category);
  setCell_(cellAt_(t, ROW.category, 3, GRID_STARTS.r0), d.subplan);

  // 經費、執行率
  setCell_(cellAt_(t, ROW.money, 2, GRID_STARTS.money), s.capital);
  setCell_(cellAt_(t, ROW.money, 4, GRID_STARTS.money), s.recurring);
  setCell_(cellAt_(t, ROW.money, 6, GRID_STARTS.money), s.total);
  setCell_(cellAt_(t, ROW.rate, 2, GRID_STARTS.money), s.capitalRate);
  setCell_(cellAt_(t, ROW.rate, 4, GRID_STARTS.money), s.recurringRate);
  setCell_(cellAt_(t, ROW.rate, 6, GRID_STARTS.money), s.totalRate);

  setCell_(cellAt_(t, ROW.budget, 1, GRID_STARTS.wide), s.budgetText);

  // 執行重點（前 16 筆進主表，其餘放續表）
  const acts = s.activities || [];
  const cap = ROW.actLast - ROW.actFirst + 1;
  acts.slice(0, cap).forEach((a, i) => {
    const r = ROW.actFirst + i;
    setCell_(cellAt_(t, r, 1, GRID_STARTS.act), a.date);
    setCell_(cellAt_(t, r, 2, GRID_STARTS.act), a.title);
    setCell_(cellAt_(t, r, 3, GRID_STARTS.act), a.summary);
    const stars = Math.max(0, Math.min(5, Number(a.stars) || 0));
    if (stars) {
      const c = cellAt_(t, r, 3 + stars, GRID_STARTS.act);
      setCell_(c, '★');
      c.getChild(0).asParagraph().setAlignment(DocumentApp.HorizontalAlignment.CENTER);
    }
  });

  // 實施效益、檢討修正、亮點、困難
  setCell_(cellAt_(t, ROW.qual, 2, GRID_STARTS.r23), s.qual);
  setCell_(cellAt_(t, ROW.qual, 4, GRID_STARTS.r23), s.quant);
  setCell_(cellAt_(t, ROW.review, 1, GRID_STARTS.pair), s.review);
  setCell_(cellAt_(t, ROW.review, 2, GRID_STARTS.pair), s.revise);
  setCell_(cellAt_(t, ROW.highlight, 1, GRID_STARTS.wide), s.highlights);
  setCell_(cellAt_(t, ROW.problem, 1, GRID_STARTS.wide), s.problems);

  // PLC 社群（巢狀表格）
  fillPlc_(cellAt_(t, ROW.plc, 1, GRID_STARTS.wide), s.plcMembers || [], s.plcMeetings || []);

  // 相片
  const photos = s.photos || [];
  const slots = ROW.photoPairs * 2;
  photos.slice(0, slots).forEach((ph, i) => {
    const pair = Math.floor(i / 2), side = 1 + (i % 2);
    const imgRow = ROW.photoFirst + pair * 2;
    try { putImage_(cellAt_(t, imgRow, side, GRID_STARTS.pair), ph.fileId); }
    catch (e) { setCell_(cellAt_(t, imgRow, side, GRID_STARTS.pair), '（圖片讀取失敗）'); }
    setCell_(cellAt_(t, imgRow + 1, side, GRID_STARTS.pair), ph.caption);
  });

  // 總體評估
  if (s.overall) tick_(cellAt_(t, ROW.overall, 1, GRID_STARTS.wide), s.overall);

  // 全部文字改黑色（模板的提示字原本是紅色、灰色）
  blackenAll_(body);

  // 續表（超過模板容量時，接在主表格後面）
  const extraActs = acts.slice(cap);
  const extraPhotos = photos.slice(slots);
  let idx = body.getChildIndex(t) + 1;
  if (extraActs.length) {
    body.insertParagraph(idx++, '（續）執行重點及自評').editAsText().setBold(true);
    const rows = [['日期', '項目名稱', '內容摘要', '自評']].concat(
      extraActs.map(a => [a.date || '', a.title || '', a.summary || '', '★'.repeat(Number(a.stars) || 0)]));
    const ct = body.insertTable(idx++, rows);
    ct.editAsText().setBold(false);
    ct.getRow(0).editAsText().setBold(true);
  }
  if (extraPhotos.length) {
    body.insertParagraph(idx++, '（續）相片或圖檔').editAsText().setBold(true);
    const rows = [];
    for (let i = 0; i < extraPhotos.length; i += 2) {
      rows.push(['', '']);
      rows.push([extraPhotos[i].caption || '', (extraPhotos[i + 1] || {}).caption || '']);
    }
    const pt = body.insertTable(idx++, rows);
    pt.editAsText().setBold(false);
    for (let i = 0; i < extraPhotos.length; i++) {
      const cell = pt.getRow(Math.floor(i / 2) * 2).getCell(i % 2);
      try { putImage_(cell, extraPhotos[i].fileId); } catch (e) { setCell_(cell, '（圖片讀取失敗）'); }
    }
  }
}

/** 把整份文件（段落、表格、巢狀表格）的文字都設成黑色。 */
function blackenAll_(body) {
  for (let i = 0; i < body.getNumChildren(); i++) {
    const el = body.getChild(i);
    const type = el.getType();
    if (type === DocumentApp.ElementType.PARAGRAPH || type === DocumentApp.ElementType.LIST_ITEM ||
        type === DocumentApp.ElementType.TABLE) {
      const t = el.editAsText();
      if (t.getText().length) t.setForegroundColor(BLACK);
    }
  }
}

function fillPlc_(cell, members, meetings) {
  const tables = [];
  for (let i = 0; i < cell.getNumChildren(); i++) {
    const ch = cell.getChild(i);
    if (ch.getType() === DocumentApp.ElementType.TABLE) tables.push(ch.asTable());
  }
  if (tables.length < 2) return;
  const [mt, wt] = tables;

  // 成員表：每列兩位
  const memberRows = Math.ceil(members.length / 2);
  while (mt.getNumRows() - 1 < memberRows) mt.appendTableRow(mt.getRow(mt.getNumRows() - 1).copy());
  for (let i = 0; i < members.length; i++) {
    const row = mt.getRow(1 + Math.floor(i / 2));
    const base = (i % 2) * 2;
    setCell_(row.getCell(base), members[i].name);
    setCell_(row.getCell(base + 1), members[i].field);
  }

  // 運作模式表
  while (wt.getNumRows() - 1 < meetings.length) wt.appendTableRow(wt.getRow(wt.getNumRows() - 1).copy());
  for (let i = 0; i < meetings.length; i++) {
    const row = wt.getRow(1 + i);
    setCell_(row.getCell(0), meetings[i].when);
    setCell_(row.getCell(1), meetings[i].topic);
    setCell_(row.getCell(2), meetings[i].note);
  }
}

/* 編輯器內測試：用假資料產生一份「測試」文件到 reference 以外的 _測試 資料夾 */
function testBuild() {
  const data = {
    subplan: '_測試', year: 115, doc: null,
    sheet: {
      months: '8～10月', fillDate: '115年10月14日', category: '學生學習',
      capital: '0', recurring: '99,000', total: '99,000',
      capitalRate: '0%', recurringRate: '35%', totalRate: '35%',
      budgetText: '1. 學生課程活動：\n1.1 服務學習：測試',
      activities: Array.from({ length: 18 }, (_, i) => ({ date: '9/' + (i + 1), title: '測試活動' + (i + 1), summary: '測試摘要', stars: 4 })),
      qual: '1. 質化測試', quant: '1. 量化測試 20 人', review: '檢討測試', revise: '修正測試',
      highlights: '■ 亮點一：測試', problems: '1. 測試',
      plcMembers: [{ name: '王小明', field: '數學' }, { name: '李小華', field: '英文' }],
      plcMeetings: [{ when: '09/01/10:00-12:00', topic: '測試會議', note: '' }],
      photos: [], overall: '好',
    },
  };
  Logger.log(JSON.stringify(buildDoc_({ data: data })));
}

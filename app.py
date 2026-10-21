"""永平高中優質化・子計畫自主管理檢核表（秋楓樣式）。

執行：streamlit run app.py
"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from core import ai, media, model, sheet, style
from core.storage import CONFIG_NAME, StoreError, make_store

st.set_page_config(page_title="優高檢核表", layout="wide", initial_sidebar_state="expanded")
st.markdown(style.CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------- 設定與連線

def secret(key: str) -> str:
    try:
        v = st.secrets.get(key, "")
    except Exception:  # 沒有 secrets.toml 時
        v = ""
    # 去掉貼上時可能夾帶的空白、換行與全形空白
    return str(v or os.environ.get(key, "")).strip().strip("\u3000")


@st.cache_resource
def get_store():
    return make_store({"GAS_WEBHOOK_URL": secret("GAS_WEBHOOK_URL"), "GAS_SECRET": secret("GAS_SECRET")})


store = get_store()


def anthropic_key() -> str:
    """讀取 AI 金鑰。

    Streamlit Cloud 的 Secrets 編輯框會把 sk-ant- 開頭的金鑰顯示成「•」，
    存檔時可能把圓點當成內容存進去，所以也接受 base64 編碼的 ANTHROPIC_API_KEY_B64。
    """
    import base64

    key = secret("ANTHROPIC_API_KEY")
    if key and "•" not in key:
        return key
    b64 = secret("ANTHROPIC_API_KEY_B64")
    if b64:
        try:
            return base64.b64decode(b64).decode("ascii").strip()
        except Exception:
            pass
    return key


API_KEY = anthropic_key()


def login_gate():
    pw = secret("APP_PASSWORD")
    if not pw or st.session_state.get("auth"):
        return
    st.markdown(style.hero("優高檢核表", "永平高中優質化計畫・子計畫自主管理檢核", "請登入"), unsafe_allow_html=True)
    with st.form("login"):
        typed = st.text_input("通關密碼", type="password")
        if st.form_submit_button("進入"):
            if typed == pw:
                st.session_state.auth = True
                st.rerun()
            st.error("密碼不正確")
    st.stop()


login_gate()


def load_config() -> dict:
    if "config" not in st.session_state:
        try:
            cfg = store.read_json(None, CONFIG_NAME) or {}
        except StoreError as e:
            st.error(str(e))
            cfg = {}
        cfg.setdefault("subplans", list(model.DEFAULT_SUBPLANS))
        st.session_state.config = cfg
    return st.session_state.config


def data_key(subplan: str, year: int) -> str:
    return f"{subplan}|{year}"


def load_data(subplan: str, year: int, force: bool = False) -> dict:
    cache = st.session_state.setdefault("data_cache", {})
    key = data_key(subplan, year)
    if force or key not in cache:
        with st.spinner("讀取雲端資料…"):
            try:
                d = store.read_json(subplan, model.data_filename(year))
            except StoreError as e:
                st.error(str(e))
                st.stop()
        cache[key] = d or model.new_data(subplan, year)
    return cache[key]


def save_data(data: dict, rebuild: bool = True) -> bool:
    """存檔；雲端模式下同時更新 Google 文件。"""
    ok = True
    if rebuild and store.remote:
        try:
            with st.spinner("更新 Google 文件中（照片多時約需 1～2 分鐘）…"):
                data["doc"] = store.build_doc(sheet.doc_payload(data))
        except StoreError as e:
            st.error(f"Google 文件更新失敗：{e}")
            ok = False
    data["updated_at"] = model.now_iso()
    try:
        store.write_json(data["subplan"], model.data_filename(data["year"]), data)
    except StoreError as e:
        st.error(f"資料存檔失敗：{e}")
        return False
    return ok


def example_block() -> dict | None:
    """從 reference 資料夾取一份 PDF 範例，給 AI 參考寫作風格。"""
    if "example_block" in st.session_state:
        return st.session_state.example_block
    blk = None
    try:
        refs = [r for r in store.get_reference() if r["mimeType"] == "application/pdf"]
        if refs:
            f = store.get_file(refs[0]["id"])
            blk = {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": f["base64"]}}
    except StoreError as e:
        st.warning(f"範例讀取失敗，改用內建寫作規範：{e}")
    st.session_state.example_block = blk
    return blk


def require_api_key():
    if not API_KEY:
        st.error("尚未設定 ANTHROPIC_API_KEY，請在 secrets 中加入後重新啟動。")
        st.stop()


# ---------------------------------------------------------------- 側欄

cfg = load_config()

st.markdown(
    style.hero("優高檢核表", "永平高中優質化計畫・各項子計畫執行情形自我檢核表"),
    unsafe_allow_html=True,
)

# 頁首下方：選擇子計畫
if st.session_state.get("pick_subplan") not in cfg["subplans"]:
    st.session_state.pick_subplan = "A-學" if "A-學" in cfg["subplans"] else cfg["subplans"][0]
with st.container(key="picker"):
    subplan = st.segmented_control("子計畫", cfg["subplans"], key="pick_subplan") or cfg["subplans"][0]

# 學年度依今天日期自動判斷（計畫期程一年：8 月～隔年 7 月）
year = model.current_year()

with st.sidebar:
    st.markdown(f"### {style.maple_svg(20)} 優高檢核表", unsafe_allow_html=True)
    if st.button("重新讀取雲端資料", width="stretch"):
        load_data(subplan, year, force=True)
        st.rerun()
    st.divider()
    if store.remote:
        st.caption("雲端模式：資料存在 Google Drive「優高檢核專區」")
    else:
        st.warning("本機模式：尚未設定 Apps Script 網址，資料只存在這台電腦，不會產生 Google 文件。")

data = load_data(subplan, year)
DK = data_key(subplan, year)

tab_home, tab_add, tab_list, tab_plc, tab_sum, tab_set = st.tabs(
    ["總覽", "新增活動", "活動列表", "PLC 社群", "年度彙整", "設定"])


# ---------------------------------------------------------------- 總覽

def doc_links(doc: dict | None):
    if not doc:
        st.info("還沒有產生 Google 文件。新增第一筆活動後就會自動建立。")
        return
    did = doc["id"]
    c1, c2, c3 = st.columns(3)
    c1.link_button("開啟 Google 文件", doc["url"], width="stretch")
    c2.link_button("下載 PDF", f"https://docs.google.com/document/d/{did}/export?format=pdf", width="stretch")
    c3.link_button("下載 Word", f"https://docs.google.com/document/d/{did}/export?format=docx", width="stretch")


with tab_home:
    acts = data["activities"]
    n_photos = sum(1 for a in acts for p in a.get("photos", []) if p.get("include"))
    c1, c2, c3 = st.columns(3)
    c1.markdown(style.stat(len(acts), "已登錄活動"), unsafe_allow_html=True)
    c2.markdown(style.stat(n_photos, "檢核表照片"), unsafe_allow_html=True)
    c3.markdown(style.stat(data.get("updated_at") or "—", "最後更新"), unsafe_allow_html=True)

    st.markdown("#### 雲端檢核表")
    doc_links(data.get("doc"))
    if store.remote and acts and st.button("重新產生 Google 文件"):
        if save_data(data):
            st.success("已更新 Google 文件")
            st.rerun()

    if data.get("doc"):
        with st.expander("在這裡預覽 Google 文件", expanded=False):
            components.iframe(f"https://docs.google.com/document/d/{data['doc']['id']}/preview", height=900, scrolling=True)
    with st.expander("檢核表內容預覽（簡化版）", expanded=not data.get("doc")):
        st.markdown(sheet.preview_html(data), unsafe_allow_html=True)


# ---------------------------------------------------------------- 新增活動

def df_rows(df: pd.DataFrame) -> list[dict]:
    """data_editor 的表格轉成 list[dict]，略過整列空白。"""
    return [{k: ("" if pd.isna(v) else str(v)) for k, v in r.items()}
            for r in df.to_dict("records") if any(str(v).strip() for v in r.values() if not pd.isna(v))]


STAR_OPTS = ["★" * n for n in range(1, 6)]

def draft_state() -> dict:
    return st.session_state.setdefault("draft", {})


def reset_draft():
    st.session_state.draft = {}
    for k in list(st.session_state.keys()):
        if k.startswith("d_"):
            del st.session_state[k]
    st.session_state.uploader_nonce = st.session_state.get("uploader_nonce", 0) + 1


def apply_ai_result(res: dict, uploads: list[media.Upload]):
    """把 AI 結果放進表單欄位。"""
    st.session_state.d_title = res.get("title", "")
    st.session_state.d_date_display = res.get("date_display", "")
    st.session_state.d_date_start = model.parse_date(res.get("date_start")) or model.today()
    st.session_state.d_date_known = bool(model.parse_date(res.get("date_start")))
    st.session_state.d_summary = res.get("summary", "")
    st.session_state.d_branch = res.get("branch", "")
    st.session_state.d_qual = res.get("qualitative", "")
    st.session_state.d_quant = res.get("quantitative", "")
    st.session_state.d_stars = "★" * min(5, max(1, int(res.get("stars") or 4)))
    st.session_state.d_reflections = "\n".join(f"{r['name']}：{r['excerpt']}" for r in res.get("reflections", []))
    st.session_state.d_meetings = pd.DataFrame(res.get("plc_meetings") or [], columns=["when", "topic", "note"])
    st.session_state.d_teachers = pd.DataFrame(res.get("teachers") or [], columns=["name", "field"])
    by_index = {f["index"]: f for f in res.get("files", [])}
    for i, up in enumerate(uploads):
        info = by_index.get(i, {})
        st.session_state[f"d_kind_{i}"] = info.get("kind") or ("照片" if up.kind == "image" else "其他")
        st.session_state[f"d_use_{i}"] = bool(info.get("use_photo")) and up.kind in ("image", "pdf")
        st.session_state[f"d_cap_{i}"] = info.get("caption", "")


with tab_add:
    draft = draft_state()
    stage = 3 if draft.get("result") else 1
    st.markdown(style.steps(stage), unsafe_allow_html=True)

    if not draft.get("result"):
        files = st.file_uploader(
            "上傳這個活動的資料（公文、獎狀、課表、簽到表、照片、心得…可一次多選；手機可直接拍照）",
            accept_multiple_files=True,
            type=["pdf", "jpg", "jpeg", "png", "heic", "heif", "webp", "docx"],
            key=f"uploader_{st.session_state.get('uploader_nonce', 0)}",
        )
        note = st.text_area("補充說明（選填）", placeholder="例：國中部凱比機器人比賽，12 人參加，得到佳作", key="d_note")
        use_example = st.checkbox("附上 reference 的去年範例給 AI 參考（較慢、費用較高）", value=False)
        if st.button("② 交給 AI 整理", type="primary", disabled=not files and not note):
            require_api_key()
            uploads = [media.Upload(f.name, f.getvalue(), f.type or "") for f in (files or [])]
            blocks, warns = media.content_blocks(uploads)
            for w in warns:
                st.warning(w)
            ctx = {"subplan": subplan, "year": year,
                   "branches": data["settings"].get("branches") or [],
                   "example": example_block() if use_example and store.remote else None}
            try:
                with st.spinner("AI 正在閱讀檔案…（約 20～60 秒）"):
                    res = ai.extract_activity(API_KEY, blocks, note, ctx)
            except ai.AIError as e:
                st.error(str(e))
                st.stop()
            draft.update({"result": res, "uploads": uploads, "note": note})
            apply_ai_result(res, uploads)
            st.rerun()
    else:
        res, uploads = draft["result"], draft["uploads"]
        if res.get("missing"):
            st.warning("AI 看不出來、需要你補上的欄位：" + "、".join(res["missing"]))

        st.markdown("##### ③ 確認內容（可直接修改）")
        c1, c2 = st.columns([2, 1])
        c1.text_input("項目名稱", key="d_title")
        c2.text_input("日期（檢核表顯示）", key="d_date_display", help="例：8/15、8/15-16、12/5、1/16")
        c3, c4 = st.columns([1, 2])
        c3.date_input("活動第一天（排序用）", key="d_date_start")
        branches = data["settings"].get("branches") or []
        opts = [""] + branches + ([st.session_state.d_branch] if st.session_state.get("d_branch") not in branches + [""] else [])
        c4.selectbox("對應分支計畫", opts, key="d_branch")
        st.text_area("內容摘要", key="d_summary", height=80)
        c5, c6 = st.columns(2)
        c5.text_area("質化成效", key="d_qual", height=90)
        c6.text_area("量化成效", key="d_quant", height=90)
        st.select_slider("自評星等", options=STAR_OPTS, key="d_stars", help=res.get("star_reason", ""))
        if res.get("star_reason"):
            st.caption("AI 評星理由：" + res["star_reason"])
        st.text_area("學生／家長心得摘錄（姓名已遮罩，可放進執行亮點）", key="d_reflections", height=80)

        st.markdown("##### PLC 社群")
        st.caption("有成果代表老師事前有討論備課。下列是 AI 依活動推估的備課紀錄草稿，請修改成實際情況；確認寫入後會加進「PLC 社群」。")
        meet_df = st.data_editor(
            st.session_state.get("d_meetings", pd.DataFrame(columns=["when", "topic", "note"])),
            column_config={"when": "日期/時間", "topic": "社群活動/討論議題", "note": "備註"},
            num_rows="dynamic", width="stretch", key="d_meetings_editor")
        teacher_df = st.data_editor(
            st.session_state.get("d_teachers", pd.DataFrame(columns=["name", "field"])),
            column_config={"name": "教師姓名", "field": "領域(專長)"},
            num_rows="dynamic", width="stretch", key="d_teachers_editor")

        st.markdown("##### 檔案與照片")
        cols = st.columns(3)
        for i, up in enumerate(uploads):
            with cols[i % 3].container(border=True):
                thumb = media.photo_jpeg(up, 480, 70)
                if thumb:
                    st.image(thumb, width="stretch")
                st.caption(up.name)
                st.selectbox("類型", model.FILE_KINDS, key=f"d_kind_{i}", label_visibility="collapsed")
                if thumb:
                    st.checkbox("放進檢核表相片欄" + ("（第一頁）" if up.kind == "pdf" else ""), key=f"d_use_{i}")
                    st.text_input("照片說明", key=f"d_cap_{i}")

        b1, b2 = st.columns([1, 1])
        if b2.button("放棄這筆，重新上傳"):
            reset_draft()
            st.rerun()
        if b1.button("④ 確認寫入", type="primary"):
            title = st.session_state.d_title.strip() or "未命名活動"
            dstart = st.session_state.d_date_start
            subdir = media.safe_name(f"{dstart.isoformat()}_{title}")
            bar = st.progress(0.0, text="上傳檔案到雲端…")
            sources, photos = [], []
            try:
                store.ensure_folder(subplan)
                for i, up in enumerate(uploads):
                    stem = media.safe_name(Path(up.name).stem, 70)
                    if up.kind == "image":
                        meta = store.upload_file(subplan, subdir, stem + ".jpg", "image/jpeg", media.to_jpeg(up.data, 1200, 80))
                        photo_id = meta["id"]
                    else:
                        meta = store.upload_file(subplan, subdir, media.safe_name(up.name, 80),
                                                 up.mime or "application/octet-stream", up.data)
                        photo_id = None
                        if up.kind == "pdf" and st.session_state.get(f"d_use_{i}"):
                            jpg = media.pdf_first_page_jpeg(up.data)
                            if jpg:
                                photo_id = store.upload_file(subplan, subdir, stem + "_第一頁.jpg", "image/jpeg", jpg)["id"]
                    sources.append({"name": up.name, "kind": st.session_state.get(f"d_kind_{i}", "其他"),
                                    "file_id": meta["id"], "url": meta.get("url", "")})
                    if photo_id:
                        photos.append({"file_id": photo_id, "name": up.name,
                                       "caption": st.session_state.get(f"d_cap_{i}", ""),
                                       "include": bool(st.session_state.get(f"d_use_{i}"))})
                    bar.progress((i + 1) / max(1, len(uploads)), text=f"已上傳 {i + 1}/{len(uploads)}")
            except StoreError as e:
                st.error(f"上傳失敗：{e}")
                st.stop()
            refl = [ln.split("：", 1) for ln in st.session_state.d_reflections.splitlines() if ln.strip()]
            data["activities"].append({
                "id": model.new_id(),
                "title": title,
                "date_display": st.session_state.d_date_display.strip(),
                "date_start": dstart.isoformat(),
                "summary": st.session_state.d_summary.strip(),
                "branch": st.session_state.d_branch,
                "qualitative": st.session_state.d_qual.strip(),
                "quantitative": st.session_state.d_quant.strip(),
                "stars": len(st.session_state.d_stars),
                "reflections": [{"name": r[0], "excerpt": r[1] if len(r) > 1 else ""} for r in refl],
                "note": draft.get("note", ""),
                "photos": photos,
                "sources": sources,
                "created_at": model.now_iso(),
            })
            # PLC：加入備課紀錄與尚未列入的教師
            data["plc"]["meetings"] = sorted(
                data["plc"]["meetings"] + df_rows(meet_df), key=lambda m: m.get("when", ""))
            known = {m.get("name") for m in data["plc"]["members"]}
            data["plc"]["members"] += [t for t in df_rows(teacher_df) if t.get("name") and t["name"] not in known]
            bar.progress(1.0, text="寫入檢核表…")
            if save_data(data):
                reset_draft()
                st.session_state.flash = "已寫入！檢核表已更新。"
                st.rerun()

    if st.session_state.get("flash"):
        st.success(st.session_state.pop("flash"))
        doc_links(data.get("doc"))


# ---------------------------------------------------------------- 活動列表

with tab_list:
    acts = sheet.sorted_activities(data)
    if not acts:
        st.info("還沒有活動。請到「新增活動」上傳第一筆。")
    for a in acts:
        aid = a["id"]
        head = f"{a.get('date_display') or '日期待補'}　{a.get('title')}　{'★' * int(a.get('stars') or 0)}"
        with st.expander(head):
            k = f"{DK}:{aid}"
            c1, c2, c3 = st.columns([2, 1, 1])
            title = c1.text_input("項目名稱", a.get("title", ""), key=f"{k}:title")
            ddisp = c2.text_input("日期（顯示）", a.get("date_display", ""), key=f"{k}:dd")
            dstart = c3.date_input("排序日期", model.parse_date(a.get("date_start")) or model.today(), key=f"{k}:ds")
            summary = st.text_area("內容摘要", a.get("summary", ""), key=f"{k}:sum", height=70)
            c4, c5 = st.columns(2)
            qual = c4.text_area("質化成效", a.get("qualitative", ""), key=f"{k}:qual", height=80)
            quant = c5.text_area("量化成效", a.get("quantitative", ""), key=f"{k}:quant", height=80)
            stars = len(st.select_slider("自評", STAR_OPTS, value="★" * int(a.get("stars") or 4), key=f"{k}:stars"))
            photo_edits = []
            if a.get("photos"):
                st.caption("照片（勾選＝放進檢核表）")
                pc = st.columns(3)
                for j, p in enumerate(a["photos"]):
                    with pc[j % 3]:
                        inc = st.checkbox(p.get("name", f"照片{j + 1}"), p.get("include", False), key=f"{k}:inc{j}")
                        cap = st.text_input("說明", p.get("caption", ""), key=f"{k}:cap{j}", label_visibility="collapsed")
                        photo_edits.append((inc, cap))
            if a.get("sources"):
                st.caption("原始檔案：" + "、".join(
                    f"[{s['name']}]({s['url']})" if s.get("url", "").startswith("http") else s["name"]
                    for s in a["sources"]))
            b1, b2, b3 = st.columns([1, 1, 2])
            if b1.button("儲存修改", key=f"{k}:save", type="primary"):
                a.update({"title": title, "date_display": ddisp, "date_start": dstart.isoformat(),
                          "summary": summary, "qualitative": qual, "quantitative": quant, "stars": int(stars)})
                for p, (inc, cap) in zip(a.get("photos", []), photo_edits):
                    p["include"], p["caption"] = inc, cap
                if save_data(data):
                    st.success("已儲存並更新檢核表")
            sure = b3.checkbox("確定要刪除這筆", key=f"{k}:sure")
            if b2.button("刪除", key=f"{k}:del", disabled=not sure):
                data["activities"] = [x for x in data["activities"] if x["id"] != aid]
                if save_data(data):
                    st.rerun()


# ---------------------------------------------------------------- PLC 社群

with tab_plc:
    st.markdown("##### 社群成員")
    members = st.data_editor(
        pd.DataFrame(data["plc"]["members"] or [], columns=["name", "field"]),
        column_config={"name": "姓名", "field": "領域(專長)"},
        num_rows="dynamic", width="stretch", key=f"{DK}:members")
    st.markdown("##### 運作模式（社群活動紀錄）")
    meetings = st.data_editor(
        pd.DataFrame(data["plc"]["meetings"] or [], columns=["when", "topic", "note"]),
        column_config={"when": "日期/時間", "topic": "社群活動/討論議題", "note": "備註"},
        num_rows="dynamic", width="stretch", key=f"{DK}:meetings")

    if st.button("儲存 PLC 社群", type="primary"):
        data["plc"] = {"members": df_rows(members), "meetings": df_rows(meetings)}
        if save_data(data):
            st.success("已儲存並更新檢核表")

    with st.expander("從研習簽到表或議程，讓 AI 擷取會議紀錄"):
        pf = st.file_uploader("上傳簽到表／議程", accept_multiple_files=True,
                              type=["pdf", "jpg", "jpeg", "png", "heic", "docx"], key=f"{DK}:plcup")
        if st.button("AI 擷取", disabled=not pf):
            require_api_key()
            blocks, warns = media.content_blocks([media.Upload(f.name, f.getvalue(), f.type or "") for f in pf])
            for w in warns:
                st.warning(w)
            try:
                with st.spinner("擷取中…"):
                    found = ai.extract_meetings(API_KEY, blocks)
            except ai.AIError as e:
                st.error(str(e))
                st.stop()
            data["plc"]["meetings"] = df_rows(meetings) + found
            data["plc"]["members"] = df_rows(members)
            if save_data(data):
                st.success(f"已加入 {len(found)} 筆會議紀錄")
                st.rerun()


# ---------------------------------------------------------------- 年度彙整

SUM_FIELDS = [
    ("budget_text", "經費規畫與運用", 160),
    ("qual", "質化成效（留空＝自動彙整各活動）", 160),
    ("quant", "量化成效（留空＝自動彙整各活動）", 160),
    ("review", "檢討", 140),
    ("revise", "修正", 140),
    ("highlights", "執行亮點", 200),
    ("problems", "問題或執行困難", 120),
]

with tab_sum:
    summ = data["summary"]
    st.caption("按下按鈕，AI 會依本學年度所有活動草擬下列欄位；你修改後按「儲存彙整」才會寫入。")
    use_ex = st.checkbox("附上去年範例給 AI 參考", value=bool(store.remote), key="sum_example")
    if st.button("AI 依目前所有活動草擬", disabled=not data["activities"]):
        require_api_key()
        try:
            with st.spinner("AI 正在草擬（約 1～2 分鐘）…"):
                out = ai.draft_summary(API_KEY, data, example_block() if use_ex and store.remote else None)
        except ai.AIError as e:
            st.error(str(e))
            st.stop()
        for f, _, _ in SUM_FIELDS:
            st.session_state[f"{DK}:sum:{f}"] = out.get(f, "")
        st.session_state[f"{DK}:sum:overall"] = out.get("overall") or "好"
        st.session_state[f"{DK}:sum:reason"] = out.get("overall_reason", "")
        st.rerun()

    vals = {}
    for f, label, h in SUM_FIELDS:
        key = f"{DK}:sum:{f}"
        if key not in st.session_state:
            st.session_state[key] = summ.get(f, "")
        vals[f] = st.text_area(label, key=key, height=h)
    okey = f"{DK}:sum:overall"
    if okey not in st.session_state:
        st.session_state[okey] = summ.get("overall") or "好"
    overall = st.radio("總體評估", model.OVERALL, key=okey, horizontal=True)
    if st.session_state.get(f"{DK}:sum:reason"):
        st.caption("AI 建議理由：" + st.session_state[f"{DK}:sum:reason"])
    if st.button("儲存彙整", type="primary"):
        data["summary"].update(vals)
        data["summary"]["overall"] = overall
        if save_data(data):
            st.success("已儲存並更新檢核表")


# ---------------------------------------------------------------- 設定

with tab_set:
    s = data["settings"]
    st.markdown(f"##### {subplan}　{year}學年度設定")
    with st.form(f"{DK}:settings"):
        cat = st.radio("類別", model.CATEGORIES, horizontal=True,
                       index=model.CATEGORIES.index(s["category"]) if s.get("category") in model.CATEGORIES else 1)
        c1, c2 = st.columns(2)
        capital = c1.number_input("資本門預算（元）", min_value=0, value=int(s.get("capital") or 0), step=1000)
        cap_spent = c2.number_input("資本門已支用（元）", min_value=0, value=int(s.get("capital_spent") or 0), step=100)
        recurring = c1.number_input("經常門預算（元）", min_value=0, value=int(s.get("recurring") or 0), step=1000)
        rec_spent = c2.number_input("經常門已支用（元）", min_value=0, value=int(s.get("recurring_spent") or 0), step=100)
        months = st.text_input("執行月份（留空＝自動，例：8～11月）", s.get("months_override", ""))
        branches = st.text_area("分支計畫清單（一行一個，AI 會從中挑選）", "\n".join(s.get("branches") or []), height=180)
        if st.form_submit_button("儲存設定"):
            s.update({"category": cat, "capital": capital, "capital_spent": cap_spent,
                      "recurring": recurring, "recurring_spent": rec_spent,
                      "months_override": months.strip(),
                      "branches": [b.strip() for b in branches.splitlines() if b.strip()]})
            if save_data(data, rebuild=bool(data["activities"])):
                st.success("已儲存")

    st.markdown("##### 子計畫代碼清單（全校共用）")
    st.caption("只用代碼，不寫承辦人姓名。")
    sp = st.text_area("一行一個代碼", "\n".join(cfg["subplans"]), height=200, key="cfg_subplans")
    if st.button("儲存子計畫清單"):
        codes = [x.strip() for x in sp.splitlines() if x.strip() and x.strip() != "reference"]
        cfg["subplans"] = codes
        try:
            store.write_json(None, CONFIG_NAME, cfg)
            st.success("已儲存")
            st.rerun()
        except StoreError as e:
            st.error(str(e))

    with st.expander("連線檢查"):
        if st.button("測試 Apps Script 連線"):
            try:
                st.success(f"連線正常：{store.ping()}")
            except StoreError as e:
                st.error(str(e))
        if store.remote and st.button("檢查空白檢核表結構"):
            try:
                info = store.inspect_template()
                if info["check"]:
                    st.error("模板結構與預期不符：" + "；".join(info["check"]))
                else:
                    st.success(f"模板結構正確（共 {info['numRows']} 列）")
                st.json(info, expanded=False)
            except StoreError as e:
                st.error(str(e))

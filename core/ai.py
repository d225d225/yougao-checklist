"""Claude API：讀取活動資料、草擬年度彙整。"""
from __future__ import annotations

import json

import anthropic

EXTRACT_MODEL = "claude-sonnet-5-5"
SUMMARY_MODEL = "claude-opus-5-5"

STYLE_GUIDE = """\
你是新北市立永平高中「高中優質化計畫」的行政助理，協助組長填寫
「各項子計畫執行情形自我檢核表(月)」。寫作規範（依學校歷年檢核表整理）：

- 使用台灣繁體中文、學校公文語氣，精簡具體，不用浮誇形容詞。
- 日期顯示用「M/D」，例如 8/15；連續多天寫「8/15-16」，不同日寫「12/5、1/16」。
- 內容摘要 1～2 句，說明「做了什麼、對象是誰、目的」。
  例：「與頂溪國小直笛團進行管樂交流」、「到永和日照中心，陪伴老人到仁愛公園散步」。
- 質化成效寫學習收穫或影響，例：「透過日照中心服務，學生在陪伴與互動中培養同理心與責任感」。
- 量化成效一定要有數字，例：「傳愛社有20位學生參加」、「日照服務教師9人，學生60人」。
- 照片說明一句話，可在開頭加日期，例：「10.23 高一參訪北藝大」、「104班長照中心服務」。
- 學生或家長的姓名一律遮罩中間字，例：「胡*穎」、「王*明」；兩個字的姓名遮罩第二字，例：「林*」。
  身分證字號、電話、地址等個資一律不寫。
- 只能根據提供的檔案與說明撰寫。看不出來的資訊（日期、人數、名次等）不可推測或編造，
  該欄留空字串，並把欄位名稱列在 missing 中。
- 例外：PLC 社群「運作模式」。有成果代表教師事前一定有討論、備課，請依活動內容與日期，
  推估活動前的教師社群備課紀錄（發想、分工、共備、試作修正、彩排等），作為草稿讓組長修改。
"""

EXTRACT_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "項目名稱，10 字以內為佳"},
        "date_start": {"type": "string", "description": "活動第一天，YYYY-MM-DD（西元）；看不出來則空字串"},
        "date_display": {"type": "string", "description": "檢核表日期欄顯示文字，例如 8/15 或 8/15-16"},
        "summary": {"type": "string"},
        "branch": {"type": "string", "description": "對應的分支計畫，必須是清單中的一項，或空字串"},
        "qualitative": {"type": "string"},
        "quantitative": {"type": "string"},
        "stars": {"type": "integer", "description": "建議自評星等 1～5"},
        "star_reason": {"type": "string"},
        "files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "kind": {"type": "string", "enum": ["照片", "公文", "獎狀", "課表", "簽到表", "心得", "其他"]},
                    "use_photo": {"type": "boolean", "description": "是否建議放進檢核表的相片欄（照片，或獎狀 PDF 的第一頁）"},
                    "caption": {"type": "string", "description": "建議放進檢核表的照片說明；非照片可留空"},
                },
                "required": ["index", "kind", "use_photo", "caption"],
                "additionalProperties": False,
            },
        },
        "reflections": {
            "type": "array",
            "description": "學生或家長心得摘錄，姓名已遮罩",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "excerpt": {"type": "string"}},
                "required": ["name", "excerpt"],
                "additionalProperties": False,
            },
        },
        "missing": {"type": "array", "items": {"type": "string"}},
        "teachers": {
            "type": "array",
            "description": "檔案中出現的指導老師、帶隊教師（教師姓名不需遮罩）；領域看不出來就空字串",
            "items": {
                "type": "object",
                "properties": {"name": {"type": "string"}, "field": {"type": "string"}},
                "required": ["name", "field"],
                "additionalProperties": False,
            },
        },
        "plc_meetings": {
            "type": "array",
            "description": "推估的教師社群備課紀錄 3～6 筆，依時間排序，日期在活動之前（最後一筆可為活動當天）",
            "items": {
                "type": "object",
                "properties": {
                    "when": {"type": "string", "description": "MM/DD/HH:MM-HH:MM，例如 09/03/12:10-13:10"},
                    "topic": {"type": "string", "description": "社群活動/討論議題，一句話"},
                    "note": {"type": "string", "description": "備註，簡短"},
                },
                "required": ["when", "topic", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "date_start", "date_display", "summary", "branch", "qualitative",
                 "quantitative", "stars", "star_reason", "files", "reflections", "missing",
                 "teachers", "plc_meetings"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "budget_text": {"type": "string"},
        "qual": {"type": "string"},
        "quant": {"type": "string"},
        "review": {"type": "string"},
        "revise": {"type": "string"},
        "highlights": {"type": "string"},
        "problems": {"type": "string"},
        "overall": {"type": "string", "enum": ["卓越", "好", "普通", "待改善"]},
        "overall_reason": {"type": "string"},
    },
    "required": ["budget_text", "qual", "quant", "review", "revise", "highlights",
                 "problems", "overall", "overall_reason"],
    "additionalProperties": False,
}

MEETING_SCHEMA = {
    "type": "object",
    "properties": {
        "meetings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "when": {"type": "string", "description": "MM/DD/HH:MM-HH:MM，例如 09/05/10:10-12:00"},
                    "topic": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["when", "topic", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["meetings"],
    "additionalProperties": False,
}


class AIError(RuntimeError):
    pass


def _client(api_key: str) -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=api_key, timeout=600, max_retries=3)


def _call_json(api_key: str, model: str, effort: str, system: str, content: list, schema: dict) -> dict:
    """呼叫 Claude 並以 JSON schema 限制輸出格式。

    啟用 server-side fallback：若安全分類器拒答，API 會自動改用備援模型。
    """
    client = _client(api_key)
    try:
        with client.messages.stream(
            model=model,
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": content}],
            extra_headers={"anthropic-beta": "server-side-fallback-2026-07-01"},
            extra_body={
                "fallbacks": "default",
                "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            },
        ) as stream:
            msg = stream.get_final_message()
    except anthropic.AuthenticationError as e:
        import hashlib
        fp = hashlib.sha256(api_key.encode()).hexdigest()[:8]
        hint = f"金鑰長度 {len(api_key)}，指紋 {fp}；服務回應：{e.message}"
        raise AIError(f"ANTHROPIC_API_KEY 無效，請檢查 secrets 設定（{hint}）") from e
    except anthropic.RateLimitError as e:
        raise AIError("AI 使用量暫時達到上限，請稍後再試") from e
    except anthropic.BadRequestError as e:
        raise AIError(f"AI 請求格式錯誤：{e.message}") from e
    except anthropic.APIStatusError as e:
        raise AIError(f"AI 服務錯誤（{e.status_code}），請稍後再試") from e
    except anthropic.APIConnectionError as e:
        raise AIError("連不上 AI 服務，請檢查網路") from e

    if msg.stop_reason == "refusal":
        raise AIError("AI 拒絕處理這些檔案，請改用文字說明或移除可能敏感的檔案")
    if msg.stop_reason == "max_tokens":
        raise AIError("AI 回覆太長被截斷，請減少一次上傳的檔案數量")
    text = next((b.text for b in msg.content if b.type == "text"), "")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise AIError("AI 回傳格式異常，請再試一次") from e


def extract_activity(api_key: str, blocks: list[dict], note: str, ctx: dict) -> dict:
    """讀取一個活動的所有檔案，產生檢核表的一列。"""
    branches = "\n".join(f"- {b}" for b in ctx["branches"]) or "（無）"
    intro = (
        f"子計畫：{ctx['subplan']}；{ctx['year']}學年度"
        f"（計畫期程為 {ctx['year'] + 1911} 年 8 月～{ctx['year'] + 1912} 年 7 月）。\n"
        f"可選的分支計畫：\n{branches}\n\n"
        f"組長補充說明：{note or '（無）'}\n\n"
        "請讀取以下所有檔案，整理成檢核表的一筆「執行重點」。"
        "files 陣列要涵蓋每一個檔案編號；照片挑 2～4 張最能呈現活動的設 use_photo=true，獎狀也設 use_photo=true 並寫說明。"
        "另外請列出指導老師（teachers），並推估活動前的教師社群備課紀錄（plc_meetings）。"
    )
    content = [{"type": "text", "text": intro}] + blocks
    if ctx.get("example"):
        content = [ctx["example"], {"type": "text", "text": "↑ 以上是學校去年已填好的檢核表範例，僅供參考寫作風格。"}] + content
    return _call_json(api_key, EXTRACT_MODEL, "medium", STYLE_GUIDE, content, EXTRACT_SCHEMA)


def draft_summary(api_key: str, data: dict, example: dict | None = None) -> dict:
    """依全年度活動草擬彙整欄位。"""
    s = data["settings"]
    acts = [
        {k: a.get(k) for k in ("date_display", "title", "branch", "summary", "qualitative",
                               "quantitative", "stars", "reflections")}
        for a in sorted(data["activities"], key=lambda a: a.get("date_start") or "9999")
    ]
    brief = {
        "子計畫": data["subplan"], "學年度": data["year"],
        "經常門預算": s.get("recurring"), "經常門已支用": s.get("recurring_spent"),
        "資本門預算": s.get("capital"), "資本門已支用": s.get("capital_spent"),
        "活動": acts,
        "PLC社群會議": data["plc"]["meetings"],
    }
    task = (
        "請依下列本學年度資料，草擬檢核表的彙整欄位：\n"
        "- budget_text（經費規畫與運用）：用「1. 學生課程活動：」「1.1 服務學習：…」分層條列，依類別歸納活動。\n"
        "- qual（質化成效）、quant（量化成效）：逐項編號「1. 2. 3.」，量化每項都要有人數或場次。\n"
        "- review（檢討）與 revise（修正）：依審查委員建議，用「改進重點－行動方式－成果指標」的結構，"
        "並呈現課程滾動修正與學生回饋。\n"
        "- highlights（執行亮點）：2～4 個「■ 亮點一：標題」，每個附日期、人數、具體做法，可引用已遮罩姓名的學生心得。\n"
        "- problems（問題或執行困難）：條列，務實具體。\n"
        "- overall：卓越/好/普通/待改善 擇一，並在 overall_reason 說明理由。\n"
        "資料不足之處寫「（待補）」，不要編造數字。\n\n"
        + json.dumps(brief, ensure_ascii=False, indent=1)
    )
    content = [{"type": "text", "text": task}]
    if example:
        content = [example, {"type": "text", "text": "↑ 學校去年已填好的檢核表範例，僅供參考寫作風格。"}] + content
    return _call_json(api_key, SUMMARY_MODEL, "high", STYLE_GUIDE, content, SUMMARY_SCHEMA)


def extract_meetings(api_key: str, blocks: list[dict]) -> list[dict]:
    """從研習簽到表、議程擷取 PLC 社群會議紀錄。"""
    content = [{"type": "text", "text": "請從以下研習簽到表或議程，擷取教師社群（PLC）的會議紀錄。"}] + blocks
    return _call_json(api_key, EXTRACT_MODEL, "low", STYLE_GUIDE, content, MEETING_SCHEMA)["meetings"]

"""把 App 資料整理成要寫進 Google 文件的內容（sheet），並產生網頁預覽。"""
from __future__ import annotations

import html

from . import model


def _money(n) -> str:
    try:
        return f"{int(round(float(n))):,}"
    except (TypeError, ValueError):
        return "0"


def _rate(spent, budget) -> str:
    try:
        b = float(budget)
        return f"{round(float(spent) / b * 100)}%" if b > 0 else "0"
    except (TypeError, ValueError):
        return "0"


def months_text(data: dict) -> str:
    s = data["settings"]
    if s.get("months_override"):
        return s["months_override"]
    if model.current_year() == data["year"]:
        end = model.today().month  # 計畫進行中：算到這個月
    else:
        end = 7  # 已結束的學年度：8～7月
    return f"8～{end}月"


def sorted_activities(data: dict) -> list[dict]:
    return sorted(data["activities"], key=model.sort_key)


def _numbered(items: list[str]) -> str:
    items = [x.strip() for x in items if x and x.strip()]
    return "\n".join(f"{i}. {x}" for i, x in enumerate(items, 1))


def build_sheet(data: dict) -> dict:
    s = data["settings"]
    summ = data["summary"]
    acts = sorted_activities(data)
    capital, recurring = s.get("capital") or 0, s.get("recurring") or 0
    cap_spent, rec_spent = s.get("capital_spent") or 0, s.get("recurring_spent") or 0

    photos = []
    for a in acts:
        for p in a.get("photos", []):
            if p.get("include") and p.get("file_id"):
                photos.append({"fileId": p["file_id"], "caption": p.get("caption", "")})

    return {
        "months": months_text(data),
        "fillDate": model.roc_date(),
        "category": s.get("category", ""),
        "capital": _money(capital),
        "recurring": _money(recurring),
        "total": _money(float(capital) + float(recurring)),
        "capitalRate": _rate(cap_spent, capital),
        "recurringRate": _rate(rec_spent, recurring),
        "totalRate": _rate(float(cap_spent) + float(rec_spent), float(capital) + float(recurring)),
        "budgetText": summ.get("budget_text", ""),
        "activities": [
            {"date": a.get("date_display", ""), "title": a.get("title", ""),
             "summary": a.get("summary", ""), "stars": a.get("stars", 0)}
            for a in acts
        ],
        # 彙整頁沒寫時，自動用各活動的成效逐項編號
        "qual": summ.get("qual") or _numbered([a.get("qualitative", "") for a in acts]),
        "quant": summ.get("quant") or _numbered([a.get("quantitative", "") for a in acts]),
        "review": summ.get("review", ""),
        "revise": summ.get("revise", ""),
        "highlights": summ.get("highlights", ""),
        "problems": summ.get("problems", ""),
        "plcMembers": data["plc"]["members"],
        "plcMeetings": data["plc"]["meetings"],
        "photos": photos,
        "overall": summ.get("overall", ""),
    }


def doc_payload(data: dict) -> dict:
    return {
        "subplan": data["subplan"], "year": data["year"],
        "doc": data.get("doc"), "sheet": build_sheet(data),
    }


def preview_html(data: dict) -> str:
    """網頁上的檢核表預覽（簡化版，正式版以 Google 文件為準）。"""
    sh = build_sheet(data)
    e = lambda x: html.escape(str(x or "")).replace("\n", "<br>")  # noqa: E731
    cats = " ".join(("■" if c == sh["category"] else "□") + c for c in model.CATEGORIES)
    overall = " ".join(("■" if o == sh["overall"] else "□") + o for o in model.OVERALL)
    rows = "".join(
        f"<tr><td>{e(a['date'])}</td><td>{e(a['title'])}</td><td>{e(a['summary'])}</td>"
        f"<td class='star'>{'★' * int(a['stars'] or 0)}</td></tr>"
        for a in sh["activities"]
    ) or "<tr><td colspan='4' class='muted'>尚無活動</td></tr>"
    ms = sh["plcMembers"]
    member_rows = "".join(
        "<tr>" + "".join(f"<td>{e(m.get('name'))}</td><td>{e(m.get('field'))}</td>" for m in ms[i:i + 2])
        + ("<td></td><td></td>" if len(ms[i:i + 2]) == 1 else "") + "</tr>"
        for i in range(0, len(ms), 2)) or "<tr><td colspan='4' class='muted'>尚無成員</td></tr>"
    meeting_rows = "".join(
        f"<tr><td>{e(m.get('when'))}</td><td>{e(m.get('topic'))}</td><td>{e(m.get('note'))}</td></tr>"
        for m in sh["plcMeetings"]) or "<tr><td colspan='3' class='muted'>尚無紀錄</td></tr>"
    plc = (
        "1. 成員<table><tr><th>姓名</th><th>領域(專長)</th><th>姓名</th><th>領域(專長)</th></tr>"
        f"{member_rows}</table>"
        "2. 運作模式<table><tr><th>日期/時間</th><th>社群活動/討論議題</th><th>備註</th></tr>"
        f"{meeting_rows}</table>")
    return f"""
<div class="pv">
  <div class="pv-title">永平高中{data['year']}學年度高中優質化計畫<br>各項子計畫執行情形自我檢核表(月)</div>
  <div class="pv-meta">執行月份：{e(sh['months'])}　　填表日期：{e(sh['fillDate'])}</div>
  <table>
    <tr><th>類別</th><td colspan="2">{e(cats)}</td><th>子計畫名稱</th><td>{e(data['subplan'])}</td></tr>
    <tr><th>經費</th><td>資本門 {e(sh['capital'])}</td><td>經常門 {e(sh['recurring'])}</td><td colspan="2">總金額 {e(sh['total'])}</td></tr>
    <tr><th>執行率</th><td>{e(sh['capitalRate'])}</td><td>{e(sh['recurringRate'])}</td><td colspan="2">{e(sh['totalRate'])}</td></tr>
    <tr><th>經費規畫與運用</th><td colspan="4">{e(sh['budgetText'])}</td></tr>
  </table>
  <table><tr><th>日期</th><th>項目名稱</th><th>內容摘要</th><th>自評</th></tr>{rows}</table>
  <table>
    <tr><th>質化成效</th><td>{e(sh['qual'])}</td></tr>
    <tr><th>量化成效</th><td>{e(sh['quant'])}</td></tr>
    <tr><th>檢討</th><td>{e(sh['review'])}</td></tr>
    <tr><th>修正</th><td>{e(sh['revise'])}</td></tr>
    <tr><th>執行亮點</th><td>{e(sh['highlights'])}</td></tr>
    <tr><th>問題或執行困難</th><td>{e(sh['problems'])}</td></tr>
    <tr><th>PLC社群</th><td>{plc}</td></tr>
    <tr><th>相片</th><td>{len(sh['photos'])} 張</td></tr>
    <tr><th>總體評估</th><td>{e(overall)}</td></tr>
  </table>
</div>"""

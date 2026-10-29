"""資料結構、預設值與日期工具。"""
from __future__ import annotations

import datetime as dt
import uuid

from core import plan

DEFAULT_SUBPLANS = list(plan.SUBPLANS)
SUBPLANS_VERSION = 2  # 115 學年度起改用 115–117 計畫書的子計畫代碼

CATEGORIES = ["教師教學", "學生學習", "教師專業發展", "課程發展", "其他"]
OVERALL = ["卓越", "好", "普通", "待改善"]
FILE_KINDS = ["照片", "公文", "獎狀", "課表", "簽到表", "心得", "其他"]

# 115–117 計畫書中的分支計畫，依子計畫字母預設；設定頁可修改。
DEFAULT_BRANCHES = plan.BRANCHES


def today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date()


def current_year(d: dt.date | None = None) -> int:
    """學年度（計畫期程一年：8 月～隔年 7 月）。"""
    d = d or today()
    roc = d.year - 1911
    return roc if d.month >= 8 else roc - 1


def roc_date(d: dt.date | None = None) -> str:
    d = d or today()
    return f"{d.year - 1911}年{d.month}月{d.day}日"


def data_filename(year: int) -> str:
    return f"data_{year}.json"


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def default_branches(subplan: str) -> list[str]:
    return list(DEFAULT_BRANCHES.get(subplan[:1], []))


def new_data(subplan: str, year: int) -> dict:
    return {
        "version": 1,
        "subplan": subplan,
        "year": year,
        "settings": {
            "category": "學生學習" if "學" in subplan else "",
            "capital": 0,
            "capital_spent": 0,
            "recurring": plan.budget_total_yuan(subplan),
            "recurring_spent": 0,
            "months_override": "",
            "branches": default_branches(subplan),
            "plan_version": 2,
        },
        "activities": [],
        "plc": {"members": [], "meetings": []},
        "summary": {
            "budget_text": "", "qual": "", "quant": "", "review": "", "revise": "",
            "highlights": "", "problems": "", "overall": "",
        },
        "doc": None,
        "updated_at": "",
    }


def sort_key(activity: dict) -> str:
    return activity.get("date_start") or "9999-99-99"


def parse_date(s: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None

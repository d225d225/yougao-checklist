"""資料結構、預設值與日期工具。"""
from __future__ import annotations

import datetime as dt
import uuid

DEFAULT_SUBPLANS = [
    "A-教", "A-學", "A-輔", "A-圖",
    "B-教", "B-學", "B-輔", "B-圖",
    "C-圖", "C-秘", "D-圖",
    "E-教", "E-學", "E-圖",
]

CATEGORIES = ["教師教學", "學生學習", "教師專業發展", "課程發展", "其他"]
OVERALL = ["卓越", "好", "普通", "待改善"]
FILE_KINDS = ["照片", "公文", "獎狀", "課表", "簽到表", "心得", "其他"]

# 114 計畫書中的分支計畫，依子計畫字母預設；設定頁可修改。
DEFAULT_BRANCHES = {
    "A": [
        "A-1-1 永平小導遊", "A-1-2 SDGs議題探究之溪州川流學", "A-1-3 日語與日本文化探究",
        "A-1-4 德語與德國文化探究", "A-1-6 藝術職人創作啟發",
        "A-2-1 資訊安全基礎實務", "A-2-2 藝術方舟-策展實務", "A-2-6 自走車",
        "A-4-1 勇闖塞恩斯島", "A-4-2 小論文工作坊", "A-4-3 生命關懷體驗營",
        "A-4-4 為愛出走體驗營", "A-4-5 藝術大師面對面", "A-4-6 從0開始學AI",
        "A-4-7 駐校藝術家列車", "A-4-8 專題培訓", "A-4-9 生涯列車體驗營",
        "A-4-10 四國文化體驗營",
    ],
    "B": [
        "B-1-1 外語菁英", "B-1-2 文學閱讀", "B-2-1 小小導遊", "B-2-2 日德停看聽",
        "B-2-3 美感創思", "B-2-4 數技先鋒", "B-2-5 創客高手", "B-2-6 繪生匯影",
        "B-2-7 領袖通識", "B-2-8 科學達人", "B-2-9 SDGs溪州川流學",
        "B-2-10 SDGs永續行動家", "B-2-11 森羅萬象", "B-2-12 樂永平華",
        "B-3-1 課程諮詢及生涯輔導規劃", "B-3-2 彈性學習課程規劃",
        "B-3-3 領導力教育-幸福人生的7個習慣", "B-3-4 雙語向前行", "B-3-5 Happy SEL Hub",
    ],
}


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
            "category": "學生學習" if subplan.endswith("學") else "",
            "capital": 0,
            "capital_spent": 0,
            "recurring": 0,
            "recurring_spent": 0,
            "months_override": "",
            "branches": default_branches(subplan),
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

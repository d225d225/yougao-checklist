"""雲端（Apps Script 橋接）與本機儲存。

設定了 GAS_WEBHOOK_URL 就寫入 Google Drive；沒有設定時改存在本機 local_data/，
方便部署 Apps Script 之前先試用介面（本機模式不會產生 Google 文件）。
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import requests

CONFIG_NAME = "_config.json"


class StoreError(RuntimeError):
    pass


class GasStore:
    remote = True

    def __init__(self, url: str, secret: str):
        self.url = url
        self.secret = secret

    def _call(self, action: str, timeout: int = 120, **params):
        payload = {"secret": self.secret, "action": action, **params}
        try:
            r = requests.post(self.url, json=payload, timeout=timeout)
        except requests.RequestException as e:
            raise StoreError(f"連不上 Apps Script：{e}") from e
        try:
            body = r.json()
        except ValueError as e:
            raise StoreError(
                f"Apps Script 回傳的不是 JSON（HTTP {r.status_code}）。"
                "常見原因：檔案太大（超過約 3MB），或部署的存取權不是「任何人」。"
            ) from e
        if not body.get("ok"):
            raise StoreError(f"Apps Script 錯誤：{body.get('error')}")
        return body.get("result")

    def ping(self):
        return self._call("ping", timeout=30)

    def read_json(self, subplan: str | None, name: str):
        return self._call("readJson", subplan=subplan, name=name)

    def write_json(self, subplan: str | None, name: str, content) -> None:
        self._call("writeJson", subplan=subplan, name=name, content=content)

    def ensure_folder(self, subplan: str) -> str:
        return self._call("ensureFolder", subplan=subplan)

    def upload_file(self, subplan: str, subdir: str, name: str, mime: str, data: bytes) -> dict:
        return self._call(
            "uploadFile", timeout=300, subplan=subplan, subdir=subdir, name=name,
            mimeType=mime, base64=base64.b64encode(data).decode("ascii"),
        )

    def build_doc(self, data: dict) -> dict:
        return self._call("buildDoc", timeout=360, data=data)

    def get_reference(self) -> list[dict]:
        return self._call("getReference")

    def get_file(self, file_id: str) -> dict:
        return self._call("getFile", timeout=180, fileId=file_id)

    def inspect_template(self) -> dict:
        return self._call("inspectTemplate")


class LocalStore:
    remote = False

    def __init__(self, root: Path):
        self.root = root

    def _folder(self, subplan: str | None) -> Path:
        p = self.root / subplan if subplan else self.root
        p.mkdir(parents=True, exist_ok=True)
        return p

    def ping(self):
        return "local"

    def read_json(self, subplan, name):
        f = self._folder(subplan) / name
        return json.loads(f.read_text("utf-8")) if f.exists() else None

    def write_json(self, subplan, name, content) -> None:
        (self._folder(subplan) / name).write_text(json.dumps(content, ensure_ascii=False, indent=1), "utf-8")

    def ensure_folder(self, subplan):
        return str(self._folder(subplan))

    def upload_file(self, subplan, subdir, name, mime, data):
        d = self._folder(subplan) / "原始資料" / subdir
        d.mkdir(parents=True, exist_ok=True)
        f = d / name
        f.write_bytes(data)
        return {"id": str(f), "url": f.as_uri()}

    def build_doc(self, data):
        return None

    def get_reference(self):
        return []

    def get_file(self, file_id):
        raise StoreError("本機模式無法讀取雲端檔案")

    def inspect_template(self):
        raise StoreError("本機模式無法檢查模板")


def make_store(secrets) -> GasStore | LocalStore:
    url = (secrets.get("GAS_WEBHOOK_URL") or "").strip()
    if url:
        return GasStore(url, secrets.get("GAS_SECRET", ""))
    return LocalStore(Path(__file__).resolve().parent.parent / "local_data")

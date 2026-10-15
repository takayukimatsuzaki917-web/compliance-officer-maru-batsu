"""scripts/ 配下のスクリプトから quiz パッケージを読み込めるようにする共通処理。

scripts/ のスクリプトは `python scripts/xxx.py` のように直接実行するため、
リポジトリのルートを import の検索パスに追加しておく必要がある。
"""

from __future__ import annotations

import sys
from pathlib import Path

#: リポジトリのルートフォルダ
ROOT_DIR = Path(__file__).resolve().parents[1]

#: 既定の設定ファイル
DEFAULT_CONFIG_PATH = ROOT_DIR / "config.yaml"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Windows のコンソールでも日本語が文字化けしないよう、出力を UTF-8 にする
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")

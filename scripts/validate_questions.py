"""問題データのスキーマ検証を行うスクリプト。

使い方:
    python scripts/validate_questions.py

エラーがあれば一覧を表示して終了コード1で終わる（バッチ生成時のチェックに使う）。
"""

from __future__ import annotations

import sys

from _bootstrap import DEFAULT_CONFIG_PATH  # quiz を import できるようにする（先に読み込むこと）

from quiz.config import load_config
from quiz.loader import load_questions


def main() -> int:
    """検証を実行し、終了コード（0=成功 / 1=エラーあり）を返す。"""
    config = load_config(DEFAULT_CONFIG_PATH)
    result = load_questions(config.questions_dir)

    if result.errors:
        print(f"NG: {len(result.errors)}件のエラーがあります")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    print(f"OK: {len(result.questions)}問すべてスキーマ検証に合格しました")
    return 0


if __name__ == "__main__":
    sys.exit(main())

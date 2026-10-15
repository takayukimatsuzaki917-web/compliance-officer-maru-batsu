"""類似・重複している問題がないかを調べるスクリプト。

使い方:
    python scripts/check_similarity.py              # 類似度0.75以上の組を表示
    python scripts/check_similarity.py --threshold 0.6
    python scripts/check_similarity.py --fail       # 見つかったら終了コード1
"""

from __future__ import annotations

import argparse
import sys

from _bootstrap import DEFAULT_CONFIG_PATH  # quiz を import できるようにする（先に読み込むこと）

from quiz.config import load_config
from quiz.loader import load_questions
from quiz.similarity import DEFAULT_SIMILARITY_THRESHOLD, find_similar_pairs

#: 一覧に表示する問題文の最大文字数
PREVIEW_LENGTH = 60


def _preview(text: str) -> str:
    """長い問題文を一覧表示用に短くする。"""
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH] + "…"


def main() -> int:
    """類似チェックを実行し、終了コードを返す。"""
    parser = argparse.ArgumentParser(description="問題文の類似・重複チェック")
    parser.add_argument("--threshold", type=float, default=DEFAULT_SIMILARITY_THRESHOLD, help="類似とみなすしきい値(0〜1)")
    parser.add_argument("--fail", action="store_true", help="類似の組が見つかったら終了コード1で終わる")
    args = parser.parse_args()

    result = load_questions(load_config(DEFAULT_CONFIG_PATH).questions_dir)
    if result.errors:
        print("スキーマ検証エラーがあるため中止します。先に validate_questions.py で修正してください。")
        return 1

    pairs = find_similar_pairs(result.questions, args.threshold)
    if not pairs:
        print(f"OK: 類似度 {args.threshold:.2f} 以上の組はありません（{len(result.questions)}問）")
        return 0

    print(f"類似度 {args.threshold:.2f} 以上の組が {len(pairs)} 件あります:")
    for pair in pairs:
        print(f"\n  [{pair.ratio:.2f}] {pair.first.id} ⇔ {pair.second.id}")
        print(f"    {pair.first.id}: {_preview(pair.first.statement)}")
        print(f"    {pair.second.id}: {_preview(pair.second.statement)}")
    return 1 if args.fail else 0


if __name__ == "__main__":
    sys.exit(main())

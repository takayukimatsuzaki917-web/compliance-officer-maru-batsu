"""問題データの構成（カテゴリ別件数・○✕比・難易度比・確認状態）を集計するスクリプト。

使い方:
    python scripts/question_stats.py

200問の作成計画（カテゴリ配分・○✕半々・難易度7:2:1）に沿っているかの確認に使う。
"""

from __future__ import annotations

import sys
from collections import Counter

from _bootstrap import DEFAULT_CONFIG_PATH  # quiz を import できるようにする（先に読み込むこと）

from quiz.config import load_config
from quiz.loader import load_questions
from quiz.models import CATEGORIES, DIFFICULTY_LABELS, STATUSES, answer_symbol

#: 最終的な目標問題数（カテゴリ別）
TARGET_COUNTS: dict[str, int] = {
    "内部管理・内部統制": 60,
    "保険募集規制": 90,
    "生命保険協会ガイドライン": 50,
}

#: 難易度の目標比率（基本:標準:難 = 7:2:1）
TARGET_DIFFICULTY_RATIO: dict[str, float] = {"basic": 0.7, "standard": 0.2, "hard": 0.1}

#: 「未設定」を表す表示名
UNSET_LABEL = "未設定"


def _percent(part: int, whole: int) -> str:
    """割合をパーセント表記にする。"""
    return f"{part / whole:.0%}" if whole else "-"


def main() -> int:
    """集計結果を表示し、終了コードを返す。"""
    result = load_questions(load_config(DEFAULT_CONFIG_PATH).questions_dir)
    if result.errors:
        print("スキーマ検証エラーがあるため中止します。先に validate_questions.py で修正してください。")
        return 1
    questions = result.questions
    total = len(questions)

    print(f"総問題数: {total}問\n")

    print("■ カテゴリ別（現在 / 目標）")
    by_category = Counter(q.category for q in questions)
    for category in CATEGORIES:
        print(f"  {category}: {by_category[category]} / {TARGET_COUNTS[category]}")

    print("\n■ 正解の○✕比")
    by_answer = Counter(q.answer for q in questions)
    for answer in (True, False):
        print(f"  {answer_symbol(answer)}: {by_answer[answer]}問（{_percent(by_answer[answer], total)}）")

    print("\n■ 難易度（現在の比率 / 目標）")
    by_difficulty = Counter(q.difficulty for q in questions)
    for key, label in DIFFICULTY_LABELS.items():
        count = by_difficulty[key]
        print(f"  {label}: {count}問（{_percent(count, total)} / 目標 {TARGET_DIFFICULTY_RATIO[key]:.0%}）")
    if by_difficulty[None]:
        print(f"  {UNSET_LABEL}: {by_difficulty[None]}問")

    print("\n■ 確認状態")
    by_status = Counter(q.status for q in questions)
    for status in STATUSES:
        print(f"  {status}: {by_status[status]}問")

    print("\n■ カテゴリ × ○✕")
    for category in CATEGORIES:
        in_category = [q for q in questions if q.category == category]
        maru = sum(1 for q in in_category if q.answer)
        print(f"  {category}: ○{maru} / ✕{len(in_category) - maru}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

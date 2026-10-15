"""問題文どうしの類似度を調べ、重複していそうな問題の組を見つけるモジュール。

単純な文字列類似度（difflib.SequenceMatcher）を使う。
意味が同じでも言い回しが大きく違う場合は検出できないので、最終確認は人の目で行う。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from typing import Sequence

from quiz.models import Question

#: 「重複の疑いあり」とみなす類似度の既定値（0〜1。1に近いほどそっくり）
DEFAULT_SIMILARITY_THRESHOLD = 0.75

#: 比較前に取り除く文字（空白・句読点・括弧など、意味の差になりにくいもの）
_NOISE_PATTERN = re.compile(r"[\s、。，．・「」『』（）()【】\[\]]")

#: 問題文の先頭につけた【...】の見出し（例: 【動作確認用サンプル】）
_LEADING_LABEL_PATTERN = re.compile(r"^【[^】]*】")


@dataclass(frozen=True)
class SimilarPair:
    """類似度が高い問題の組。"""

    first: Question
    second: Question
    ratio: float  # 類似度（0〜1）


def normalize_statement(statement: str) -> str:
    """類似度を測りやすいよう、問題文から見出しや記号を取り除く。"""
    without_label = _LEADING_LABEL_PATTERN.sub("", statement)
    return _NOISE_PATTERN.sub("", without_label)


def find_similar_pairs(
    questions: Sequence[Question],
    threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> list[SimilarPair]:
    """すべての問題の組み合わせについて類似度を測り、しきい値以上の組を返す。

    200問なら約2万組の比較で、数秒で終わる。

    Args:
        questions: 調べる問題。
        threshold: この値以上の類似度の組を返す。

    Returns:
        類似度の高い順に並べた SimilarPair のリスト。
    """
    normalized = [(q, normalize_statement(q.statement)) for q in questions]
    pairs: list[SimilarPair] = []
    for (q1, text1), (q2, text2) in combinations(normalized, 2):
        matcher = SequenceMatcher(None, text1, text2, autojunk=False)
        # quick_ratio は ratio の上限値で計算が速いので、先に足切りして処理を軽くする
        if matcher.quick_ratio() < threshold:
            continue
        ratio = matcher.ratio()
        if ratio >= threshold:
            pairs.append(SimilarPair(q1, q2, ratio))
    return sorted(pairs, key=lambda pair: pair.ratio, reverse=True)

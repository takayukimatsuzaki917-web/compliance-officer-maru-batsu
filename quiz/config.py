"""設定ファイル（config.yaml）を読み込むモジュール。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

#: 設定ファイルが無い・項目が欠けている場合に使う既定値
DEFAULT_NUM_QUESTIONS = 25
DEFAULT_PASS_RATIO = 0.70
DEFAULT_TIME_LIMIT_MINUTES = 30
DEFAULT_QUESTIONS_DIR = "data/questions"
DEFAULT_HISTORY_FILE = "history.json"


class ConfigError(Exception):
    """設定値が不正なときに送出する例外。"""


@dataclass(frozen=True)
class AppConfig:
    """アプリの設定値。"""

    num_questions: int  # 模試の出題数
    pass_ratio: float  # 合格ライン（0〜1の正答率）
    time_limit_minutes: int  # 模試の制限時間（分）
    questions_dir: Path  # 問題データのフォルダ
    history_file: Path  # 学習履歴ファイル


def _is_number(value: Any) -> bool:
    """bool を除く数値（int / float）なら True。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_positive_int(value: Any) -> bool:
    """bool を除く1以上の整数なら True。"""
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def load_config(config_path: Path) -> AppConfig:
    """config.yaml を読み込み、値をチェックして AppConfig を返す。

    フォルダ・ファイルの相対パスは config.yaml が置かれた場所を基準に解決する。

    Args:
        config_path: 設定ファイルのパス。

    Returns:
        AppConfig。

    Raises:
        ConfigError: 設定値の型や範囲が不正な場合。
    """
    raw: dict[str, Any] = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    exam = raw.get("exam") or {}
    paths = raw.get("paths") or {}

    num_questions = exam.get("num_questions", DEFAULT_NUM_QUESTIONS)
    pass_ratio = exam.get("pass_ratio", DEFAULT_PASS_RATIO)
    time_limit = exam.get("time_limit_minutes", DEFAULT_TIME_LIMIT_MINUTES)

    # --- 値の範囲チェック（誤った設定のまま動かないようにする） ---
    if not _is_positive_int(num_questions):
        raise ConfigError(f"exam.num_questions は1以上の整数にしてください（現在: {num_questions!r}）")
    if not _is_number(pass_ratio) or not 0 < pass_ratio <= 1:
        raise ConfigError(f"exam.pass_ratio は0より大きく1以下の数値にしてください（例: 0.7）（現在: {pass_ratio!r}）")
    if not _is_positive_int(time_limit):
        raise ConfigError(f"exam.time_limit_minutes は1以上の整数（分）にしてください（現在: {time_limit!r}）")

    base_dir = config_path.parent
    return AppConfig(
        num_questions=num_questions,
        pass_ratio=float(pass_ratio),
        time_limit_minutes=time_limit,
        questions_dir=base_dir / paths.get("questions_dir", DEFAULT_QUESTIONS_DIR),
        history_file=base_dir / paths.get("history_file", DEFAULT_HISTORY_FILE),
    )

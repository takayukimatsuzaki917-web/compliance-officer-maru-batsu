"""設定ファイル（config.yaml）読み込みのテスト。"""

from __future__ import annotations

import pytest

from conftest import ROOT_DIR
from quiz.config import ConfigError, load_config


def test_repository_config_loads():
    config = load_config(ROOT_DIR / "config.yaml")
    assert config.num_questions == 25
    assert 0 < config.pass_ratio <= 1
    assert config.time_limit_minutes >= 1
    assert config.questions_dir == ROOT_DIR / "data/questions"


def test_missing_file_uses_defaults(tmp_path):
    config = load_config(tmp_path / "none.yaml")
    assert config.num_questions == 25
    assert config.history_file == tmp_path / "history.json"


@pytest.mark.parametrize(
    "yaml_text",
    [
        "exam:\n  num_questions: 0\n",
        "exam:\n  num_questions: '25'\n",
        "exam:\n  pass_ratio: 70\n",
        "exam:\n  pass_ratio: 0\n",
        "exam:\n  time_limit_minutes: -5\n",
        "exam:\n  time_limit_minutes: true\n",
    ],
)
def test_invalid_values_raise(tmp_path, yaml_text):
    path = tmp_path / "config.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(path)

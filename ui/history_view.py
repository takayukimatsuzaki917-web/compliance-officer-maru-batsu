"""履歴画面: 過去の模試の得点推移を表示する。"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from ui.components import format_datetime, render_table
from ui.context import AppContext

#: 割合（0〜1）をパーセント（0〜100）に変換する倍率
PERCENT = 100


def render(ctx: AppContext) -> None:
    """履歴画面を描画する。"""
    st.title("模試の履歴")
    records = ctx.history.mock_records()
    if not records:
        st.info("まだ模試を受けていません。模試を受けると、ここに得点の推移が表示されます。")
        return

    # --- 得点推移のグラフ（正答率と合格ラインを重ねて表示） ---
    chart_data = pd.DataFrame(
        {
            "正答率(%)": [r.result.ratio * PERCENT for r in records],
            "合格ライン(%)": [r.result.pass_ratio * PERCENT for r in records],
        },
        index=pd.Index(range(1, len(records) + 1), name="回"),
    )
    st.line_chart(chart_data, y_label="%", x_label="回")

    # --- 一覧表（新しい順） ---
    rows = [
        [
            number,
            format_datetime(record.finished_at),
            f"{record.result.score}/{record.result.total}（{record.result.ratio:.0%}）",
            ("✔ 合格" if record.result.passed else "✘ 不合格") + ("・⏱時間切れ" if record.timed_out else ""),
        ]
        for number, record in enumerate(records, start=1)
    ]
    render_table(["回", "日時", "得点", "合否"], rows[::-1])

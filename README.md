# 法令等遵守責任者 ○×トレーニング

生命保険協会「法令等遵守責任者等資格試験」（○×形式）の対策用に作った、**非公式・個人学習用**の Web アプリです。

> [!IMPORTANT]
> **免責事項**
> - 本アプリは個人が学習用に作成した非公式アプリであり、**生命保険協会とは一切関係ありません**。
> - 問題・解説・根拠の正確性は保証しません。法令・監督指針・ガイドラインは改正されるため、**必ず最新の公式情報を確認してください**。
> - 問題はすべて自作です。市販の問題集・テキスト・協会の資料の文章は転載していません。
> - 問題データの基準日: **（200問の投入時に「○年○月時点の法令に基づく」と追記します）**

## 主な機能

| 画面 | 内容 |
|---|---|
| ホーム | 全体の進捗（解いた問題数）、直近の模試の得点、誤答・要復習の件数 |
| 模試 | 本番形式。カテゴリ比率を保った層化抽出で出題、制限時間タイマー、前の問題への戻り、「後で見直す」印、採点結果（合否・カテゴリ別正答率・全問の解説） |
| 1問1答 | 出題範囲（全問／カテゴリ／未回答／誤答／要復習）と出題順（順番通り／ランダム）を選んで学習。○✕を押すとすぐに正誤・解説・根拠・tips を表示 |
| 履歴 | 過去の模試の得点推移（グラフと一覧） |
| 設定 | draft（根拠未確認）の問題を出題に含めるかの切り替え、問題の構成、模試の設定値の確認 |

スマホのブラウザで使いやすい縦長レイアウトです（画面上部の「>>」からメニューを開けます）。

## セットアップ

Python 3.11 以上が必要です。

```bash
git clone https://github.com/takayukimatsuzaki917-web/compliance-officer-maru-batsu.git
cd compliance-officer-maru-batsu
python -m venv .venv
```

仮想環境を有効にして、必要なパッケージを入れます。

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## 起動方法

```bash
streamlit run app.py
```

ブラウザで http://localhost:8501 が開きます。スマホから使う場合は、同じネットワーク内で表示される `Network URL` にアクセスしてください。

## テスト

```bash
pytest
```

スキーマ検証・層化抽出・採点・履歴保存・設定読み込み・類似チェックのテストが実行されます。

## 設定の変更（合格ライン・制限時間など）

`config.yaml` を編集し、ブラウザを再読み込みしてください。

```yaml
exam:
  num_questions: 25        # 模試の出題数
  pass_ratio: 0.70         # 合格ライン（0.70 = 70%）
  time_limit_minutes: 30   # 制限時間（分）
```

> [!WARNING]
> **合格ライン（70%）と制限時間（30分）は仮の値です。** 公式の試験要項で確認し、必要に応じて変更してください。

## 問題の追加方法

問題は `data/questions/` 配下にカテゴリ別の JSON ファイルで置いています。ファイル内の配列に1問ずつ追加してください。

| ファイル | カテゴリ |
|---|---|
| `internal_control.json` | 内部管理・内部統制 |
| `solicitation_rules.json` | 保険募集規制 |
| `association_guidelines.json` | 生命保険協会ガイドライン |

### 1問分の形式

```json
{
  "id": "q201",
  "category": "保険募集規制",
  "subcategory": "意向把握・確認義務",
  "statement": "問題文",
  "answer": true,
  "explanation": "解説（2〜4文。✕の問題は「正しくはこう」を必ず書く）",
  "reference": "根拠（法令名・条番号、監督指針、協会ガイドライン名と章など）",
  "tip": "一言で覚えるtips（1文）",
  "status": "draft",
  "difficulty": "basic"
}
```

| 項目 | 必須 | 説明 |
|---|---|---|
| `id` | ○ | 全ファイルを通して一意。英数字・`-`・`_` のみ |
| `category` | ○ | `内部管理・内部統制` / `保険募集規制` / `生命保険協会ガイドライン` のいずれか |
| `answer` | ○ | `true`（○）または `false`（✕）。`"true"` のような文字列は不可 |
| `status` | ○ | `draft`（根拠未確認。画面に「要確認」バッジ）/ `reviewed`（一次情報で根拠を確認済み） |
| `difficulty` | 任意 | `basic`（基本）/ `standard`（標準）/ `hard`（難） |

### 追加した後のチェック

```bash
python scripts/validate_questions.py   # スキーマ検証（id重複・必須項目・不正値）
python scripts/question_stats.py       # カテゴリ別件数・○✕比・難易度比の集計
python scripts/check_similarity.py     # 類似・重複している問題の検出
```

アプリ起動時にもスキーマ検証を行い、エラーがあれば内容を画面に表示して起動を止めます。

## ディレクトリ構成

```
app.py                 アプリの入口（画面の切り替え）
config.yaml            模試の設定（出題数・合格ライン・制限時間）
quiz/                  画面に依存しないロジック（検証・抽出・採点・履歴）
ui/                    Streamlit の各画面と共通部品
data/questions/        問題データ（JSON）
scripts/               検証・集計・類似チェックのスクリプト
tests/                 pytest
docs/                  作成計画（question_plan.md）、要確認一覧（review_needed.md）
```

## 学習履歴について

- 学習履歴は `history.json`（リポジトリのルート）に保存されます。`.gitignore` の対象なので、GitHub には上がりません。
- 履歴をリセットしたい場合は、アプリを止めてから `history.json` を削除してください。
- 模試の途中経過はブラウザのセッション内だけで保持しています。模試の途中でブラウザを再読み込みすると、その模試は中断されます。

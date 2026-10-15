# 法令等遵守責任者 ○×トレーニング

生命保険協会「法令等遵守責任者等資格試験」（○×形式）の対策用に作った、**非公式・個人学習用**の Web アプリです。

> [!IMPORTANT]
> **免責事項**
> - 本アプリは個人が学習用に作成した非公式アプリであり、**生命保険協会とは一切関係ありません**。
> - 問題・解説・根拠の正確性は保証しません。法令・監督指針・ガイドラインは改正されるため、**必ず最新の公式情報を確認してください**。
> - 問題はすべて自作です。市販の問題集・テキスト・協会の資料の文章は転載していません。
> - 問題データは **2026年（令和8年）10月時点の法令・監督指針・協会ガイドラインに基づきます**。
>   - 令和7年の保険業法改正（令和7年法律第54号）は **2026年6月1日施行済み** の内容を反映しています。比較推奨販売に関する改正内閣府令（2026年8月28日公布）は **2028年3月1日施行** のため、施行前の扱いとしています。
>   - 公益通報者保護法の令和7年改正（令和7年法律第62号）は **2026年12月1日施行予定** です。関係する問題には施行日を明記しています。
>   - 監督指針は「保険会社向けの総合的な監督指針（令和8年10月）」を参照しています。

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

## どのPCからでも使う（インターネットに公開する）

[Streamlit Community Cloud](https://share.streamlit.io)（無料）にアプリを置くと、どのPCやスマホのブラウザからでもURLを開くだけで使えます。

- **学習履歴:** GitHub Gist（非公開のメモ置き場）に保存します。どの端末から解いても、同じ履歴を引き継げます。
- **パスワード:** アプリにパスワードをかけられます。URLを知っている他人に使われたり、履歴を書き換えられたりするのを防ぎます。

### 1. 履歴を保存する Gist を作る

1. GitHub にログインした状態で https://gist.github.com を開きます。
2. 「Filename including extension」に `history.json`、本文に `{}` と入力します。
3. **「Create secret gist」**（非公開）で作成します。
4. 作成後のURL `https://gist.github.com/ユーザー名/xxxxxxxx` の末尾 `xxxxxxxx` が **Gist の id** です。

### 2. Gist を読み書きするためのトークンを発行する

1. GitHub の Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → 「Generate new token」を開きます。
2. 名前と有効期限を決めます（例: 試験日の少し後まで）。
3. 「Permissions」の **Account permissions** で **Gists** を **Read and write** にします。ほかの権限は不要です。
4. 発行されたトークン（`github_pat_...`）をコピーします。トークンは一度しか表示されません。

> [!CAUTION]
> トークンはパスワードと同じ扱いです。リポジトリやチャットに貼り付けず、次の手順の Secrets にだけ設定してください。有効期限が切れたら、新しいトークンを発行して Secrets を更新します。

### 3. Streamlit Community Cloud で公開する

1. https://share.streamlit.io を開き、GitHub アカウントでログインします。
2. 「Create app」→「Deploy a public app from GitHub」を選びます。
3. 次のとおり指定します。
   - Repository: `takayukimatsuzaki917-web/compliance-officer-maru-batsu`
   - Branch: `main`
   - Main file path: `app.py`
4. 「Advanced settings」を開き、Python のバージョンを 3.12 にします。
5. 同じ画面の **Secrets** に、次の内容を貼り付けて値を書き換えます（ひな形: `.streamlit/secrets.toml.example`）。

   ```toml
   [app]
   password = "自分で決めたパスワード"

   [github]
   token = "手順2のトークン"
   gist_id = "手順1の Gist の id"
   ```

   `gist_id` には、Gist の URL（`https://gist.github.com/ユーザー名/xxxxxxxx`）をそのまま貼り付けても構いません。アプリが末尾の id を取り出して使います。

6. 「Deploy」を押すと、数分でアプリのURL（`https://〇〇.streamlit.app`）が発行されます。各端末のブラウザでブックマークしておくと便利です。

### うまく動かないとき

画面に表示される HTTP のエラー番号で、原因を切り分けられます。Secrets を直したら、Streamlit の画面右下のメニューから「Reboot app」を実行してください。

| 表示 | 主な原因 | 対処 |
|---|---|---|
| HTTP 404 | `gist_id` が違う／Gist を削除した／別のアカウントで作った Gist | Gist の URL を開けるか確認し、その URL か末尾の id を `gist_id` に設定する |
| HTTP 401 | トークンの貼り間違い・有効期限切れ | トークンを発行し直して `token` を更新する |
| HTTP 403 | トークンに Gist の権限がない | Fine-grained token の Account permissions で「Gists: Read and write」を付ける |
| gist_id の形式が正しくありません | `gist_id` に記号や日本語が混じっている | Gist の URL の末尾の英数字だけを設定する |

### 公開時の注意

- **リポジトリ:** 公開リポジトリなので、問題データやプログラムは誰でも見られます。パスワード・トークン・学習履歴は Secrets と Gist に置くため公開されません。
- **スリープ:** しばらく使わないとアプリがスリープします。開いたときに起動ボタンが表示されたら押してください（1分ほどで起動します）。履歴は Gist にあるので消えません。
- **更新の反映:** `main` に push すると、アプリにも自動で反映されます。
- **複数端末での利用:**
  - 複数の端末で同時に使っても、保存のたびに Gist の最新内容と統合するので、回答記録は失われません。
  - 要復習フラグと設定は、最後に変更した内容が優先されます。
  - 別の端末で解いた内容をすぐ反映したいときは、設定画面の「最新の履歴を読み込む」を押します。

### 自分のPCで Gist の履歴を使う場合

`.streamlit/secrets.toml.example` を `.streamlit/secrets.toml` にコピーして値を設定すると、ローカルで起動したアプリでも同じ Gist の履歴を使えます。`secrets.toml` は `.gitignore` の対象です。Secrets を設定しない場合は、従来どおりパスワードなしで、履歴はローカルの `history.json` に保存されます。

## テスト

```bash
pytest
```

スキーマ検証、層化抽出、採点、履歴保存、履歴の統合（複数端末）、保存先（ファイル／Gist）、パスワード判定、設定読み込み、類似チェックのテストが実行されます。

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
quiz/                  画面に依存しないロジック（検証・抽出・採点・履歴・保存先・認証）
ui/                    Streamlit の各画面と共通部品（ログイン・Secrets の読み出しを含む）
.streamlit/            Streamlit の設定（secrets.toml.example は Secrets のひな形）
data/questions/        問題データ（JSON）
scripts/               検証・集計・類似チェックのスクリプト
tests/                 pytest
docs/                  作成計画（question_plan.md）、要確認一覧（review_needed.md）
```

## 学習履歴について

- 保存先は設定によって変わります（設定画面の「学習履歴の保存先」で確認できます）。
  - **Secrets に GitHub の設定がある場合:** GitHub Gist の `history.json`
  - **設定がない場合:** リポジトリのルートの `history.json`（`.gitignore` の対象なので、GitHub には上がりません）
- 履歴をリセットしたい場合は、Gist の場合は Gist の内容を `{}` に書き換えます。ローカルの場合は、アプリを止めてから `history.json` を削除してください。
- 模試の途中経過はブラウザのセッション内だけで保持しています。模試の途中でブラウザを再読み込みすると、その模試は中断されます。

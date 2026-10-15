# gcheck CLI

[English](README.md) | [中文](README.zh.md) | [Español](README.es.md) | **日本語**

gcheck は、Google AI の統合プロセスを効率化するために開発者向けに特別に構築された、軽量な CLI 診断ツールです。API をテストするために一時的なスクリプトを手書きする必要はもうありません。数秒でローカル環境の設定を自動スキャンし、設定上の問題を早期に発見して、最初の「Hello Gemini」をスムーズに実行できるようサポートします。

## ✨ 主な機能

- 🚀 **Gemini API の自動診断**: Google Gemini API の呼び出しに関する問題を素早くトラブルシューティングします。ネットワーク接続、Google Cloud Platform (GCP) プロジェクトの権限、API キー、モデルパラメータの設定を自動的に検証し、これまで以上に迅速な Gemini への接続を支援します。
- 📁 **スマートなプロジェクトディレクトリスキャン**: ワークスペース内のプロジェクト設定をシームレスに検出します。ローカルの環境設定ファイル、依存関係、各種設定を分析し、隠れた統合のボトルネックを特定します。
- 🛠️ **難解なエラーに対する明確な解決策**: バグを見つけるだけでなく、修正までサポートします。分かりにくいエラーメッセージを平易で読みやすい説明に置き換え、実践的なステップバイステップのガイドを提供することで、手探りの試行錯誤をなくします。

---

## 📋 前提条件

- Python 3.10 以上
- [pipx](https://pipx.pypa.io/stable/installation/)（インストールに推奨。`pip` を直接使用する場合は不要）
- `GEMINI_API_KEY`（任意 — Gemini API の接続確認を行う場合のみ必要）

---

## 🚀 インストール

### クイックインストール（推奨）

リポジトリをクローンし、お使いの OS に対応したインストールスクリプトを実行します。このスクリプトは Python 3.10 以上と `pipx` の有無を確認（不足している場合は自動的にインストール）し、`gcheck` をグローバルかつ編集可能（editable）なコマンドとしてインストールします。コードの変更は再インストールなしで即座に反映されます：

```sh
# macOS / Linux
./install.sh
```

```powershell
# Windows (PowerShell)
.\install.ps1
```

macOS / Linux で `permission denied`（権限エラー）が表示されてスクリプトがブロックされる場合は、先に実行権限を付与してから再実行してください：

```sh
chmod +x install.sh
./install.sh
```

Windows で実行ポリシー（execution policy）のエラーによってスクリプトがブロックされる場合は、以下を実行してください：

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

インストール直後に `gcheck` コマンドが見つからない場合は、新しいターミナルウィンドウを開いてください（スクリプトによって環境変数 `PATH` が更新された直後の可能性があります）。

### 手動インストール

| コマンド | 独立した仮想環境 | グローバルな `gcheck` コマンド | 編集可能モード（コード変更が即時反映） |
|---|---|---|---|
| `pipx install --editable .`（推奨） | はい | はい | はい |
| `pipx install .` | はい | はい | いいえ — 変更後は `--force` を付けて再実行が必要 |
| `pip install -e .` | いいえ（現在アクティブな環境にインストール） | はい（その環境内のみ） | はい |
| `pip install --require-hashes -r requirements.txt` | いいえ（現在アクティブな環境にインストール） | いいえ — エントリポイントなし。`python -m gcheck` で実行 | 該当なし |

```sh
# 日常的な開発・デバッグ時に推奨
pipx install --editable .
```

`pip install --require-hashes -r requirements.txt` は、ロックファイルからハッシュ検証済みの厳密にバージョン固定された依存パッケージをインストールしますが、`gcheck` 自体はインストールしません。動作確認済みの依存関係セットを再現するためにこれを使用し、その後 `gcheck` コマンドを利用するために `pip install -e . --no-deps` を実行してください。

---

## ⚙️ 設定

任意 — API キーの接続チェックを行う場合のみ必要です。作業ディレクトリ内の `.env.example` を `.env` にコピーし、ご自身の API キーを追加してください：

```
GEMINI_API_KEY=your_api_key_here
```

---

## 💻 使い方

```sh
gcheck              # ターミナル UI (TUI) で言語を選択
gcheck --lang en    # 英語 (English)
gcheck --lang zh    # 中国語 (中文)
gcheck --lang es    # スペイン語 (Español)
gcheck --lang ja    # 日本語
```

---

## 🗑️ アンインストール

```sh
pipx uninstall gcheck
```

`pipx: command not found` と表示される場合 — `install.sh` が Homebrew ではなく `pip install --user` 経由で `pipx` をインストールした可能性があり、その場合は*新しく開いた*ターミナルウィンドウでのみ `PATH` が反映されます。新しいターミナルを開いて再試行するか、Python から直接実行してください：

```sh
python3 -m pipx uninstall gcheck
```

`pipx` ではなく `pip install -e .` でインストールした場合は、インストールした際と同じ Python 環境で `pip uninstall gcheck` を実行してください。

`pipx` 自体も削除する場合：まず `pipx uninstall-all` を実行（pipx で管理されているすべてのアプリを削除）し、その後 `pipx` のインストール方法に応じて `pip uninstall pipx` または `brew uninstall pipx` を実行してください。

---

## 🧪 テスト

ローカルにチェックアウトしたリポジトリに対してテストスイートを実行します：

```sh
pip install -e ".[test]"
pytest unit_test
```

CI は、すべての push および pull request ごとに、Ubuntu、macOS、Windows 上の Python 3.10 および 3.13 環境で同じテストスイートを実行します（詳細は [.github/workflows/unit-tests.yml](.github/workflows/unit-tests.yml) を参照）。テスト対象の範囲および意図的に除外されている項目については、[unit_test/README.md](unit_test/README.md) を参照してください。

---

## 📄 ライセンス

本プロジェクトは Apache License, Version 2.0 の下でライセンスされています。全文については [LICENSE](LICENSE) を参照してください。

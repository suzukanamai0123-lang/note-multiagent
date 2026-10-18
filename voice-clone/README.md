# 錫奏AIクローンボイス 試作環境

自分の声の参照音声（5〜10秒）とその文字起こしを渡すと、台本を自分の声で読み上げたWAVを作る。
Mac（Apple Silicon）のローカルで動かす。費用はかからない。

- エンジン: [mlx-audio](https://github.com/Blaizzy/mlx-audio) 0.5.9（MIT）
- モデル: mlx-community の Qwen3-TTS Base 8bit
  - メモリ 16GB 以上 → `Qwen3-TTS-12Hz-1.7B-Base-8bit`（約3.1GB。日本語の精度はこちらが上）
  - メモリ 8GB → `Qwen3-TTS-12Hz-0.6B-Base-8bit`（約2.0GB）
  - `scripts/setup.sh` がメモリ量を見て自動で選び、`model.txt` に記録する

## 動作条件

試作機: MacBook Air M1 / メモリ 8GB / macOS 15.7.7 → 0.6B を使う

| 項目 | 条件 |
|---|---|
| Mac | Apple Silicon（M1 以降） |
| macOS | **14 (Sonoma) 以上**。mlx（0.31〜0.32系）の配布パッケージは macOS 14 以上向けしかない |
| 空き容量 | 8GB 以上（実際に使うのは約 4〜6GB） |
| uv | 必要。無ければ `scripts/setup.sh` が y/N で確認してから、このフォルダ内の `.uv-bin/` にだけ入れる（シェル設定・Homebrew には触れない） |
| ffmpeg | 不要（WAV しか扱わない） |

## フォルダ構成

すべてこのフォルダ（`~/suzukana-voice-clone`）の中に閉じている。**フォルダごと消せば元通り**になる。
`~/clip-tools-venv`、`~/ShortsTool`、`~/clip_tools`、`~/clips_project*` には触れない。

```
~/suzukana-voice-clone/
  env.sh            保存先をこのフォルダ内に向ける設定（HF_HOME, uv の Python・キャッシュ）
  run.sh            生成コマンド（オフラインで実行）
  clone.py          生成スクリプト本体
  scripts/
    check_env.sh    Phase 1 の環境確認（読むだけ）
    setup.sh        Phase 2 の構築
  .uv-bin/          uv 本体（無かった場合のみ）     ← setup.sh が作る
  .venv/            Python 3.12 の仮想環境         ← setup.sh が作る
  .uv-python/       uv が入れた Python 3.12        ← setup.sh が作る
  .uv-cache/        uv のキャッシュ                 ← setup.sh が作る
  hf-home/          モデル置き場（HF_HOME）         ← setup.sh が作る
  model.txt         使うモデル名                    ← setup.sh が作る
  refs/             参照音声を置く場所（自分で作る。git 管理外）
  outputs/          生成結果と history.jsonl        ← clone.py が作る
  logs/             セットアップログと依存関係の一覧 ← setup.sh が作る
```

## セットアップ

```bash
# 1. このフォルダを ~/suzukana-voice-clone に置く
git clone -b claude/qwen3-tts-voice-clone-27sptn https://github.com/suzukanamai0123-lang/note-multiagent.git /tmp/note-multiagent
cp -R /tmp/note-multiagent/voice-clone ~/suzukana-voice-clone
cd ~/suzukana-voice-clone

# 2. 環境確認（読むだけ）
bash scripts/check_env.sh

# 3. 構築（uv のインストールとモデルのダウンロードの前に y/N を聞く）
bash scripts/setup.sh
```

モデルを自分で選びたいとき:

```bash
MODEL=mlx-community/Qwen3-TTS-12Hz-0.6B-Base-8bit bash scripts/setup.sh
```

`setup.sh` は何度実行しても大丈夫（済んだ手順は飛ばすか、同じ結果になる）。
入った依存関係の一覧は `logs/requirements-lock.txt` に残る。

## 参照音声の用意

- **自分の声だけ**。BGM・SE・他人の声・笑い声の重なりが無い区間を選ぶ
- 長さ 5〜10 秒。文の途中で切れない区間を選ぶ
- 文字起こしは**一字一句**合わせる（言い間違いもそのまま）。ずれると品質が落ちる
- WAV がおすすめ。元ファイルはコピーして `refs/` に置く（元データは触らない）

## 実行

```bash
cd ~/suzukana-voice-clone
./run.sh --ref-audio refs/me.wav \
  --ref-text "参照音声で話している内容をそのまま" \
  --text "こんにちは。今日は錫奏AIクローンボイスの動作確認をしています。" \
  --play
```

- `--ref-text-file` / `--text-file` でファイルからも渡せる。`--text-file` は改行ごとに分けて生成し、1つの WAV につなぐ
- `--seed` を固定すると同じ条件で比べやすい（既定 0）
- `--temperature`（既定 0.9）を下げると読みが安定し、上げると抑揚が増える
- `--name` で出力名を指定。同名ファイルがあると上書きせずに止まる

出力（`outputs/`）:

| ファイル | 中身 |
|---|---|
| `<日時>_<文頭>.wav` | 生成音声（24kHz モノラル） |
| `<日時>_<文頭>_compare.wav` | 参照音声 → 無音0.7秒 → 生成音声。聞き比べ用 |
| `history.jsonl` | 1生成1行。入力文、参照音声のパスと SHA-256、モデル、バージョン、設定、生成時間、ピークメモリ、エラー内容 |

再生: `afplay outputs/xxx_compare.wav`、または Finder でクイックルック（スペースキー）。

## 試作の評価（Phase 5 の判断材料）

同じ参照音声で、性格の違う 5 文ほど（あいさつ、早口、固有名詞、感情が乗る文、長めの文）を生成して、`_compare.wav` を聞いて次の観点で付ける。

| 観点 | 見ること | 1〜5 |
|---|---|---|
| 声の似かた | 声質・高さ・息の感じが本人と思えるか | |
| 日本語の正しさ | 読み間違い、アクセント、抜け・繰り返し | |
| 自然さ | 間・抑揚・語尾 | |
| 安定性 | seed を変えて 3 回作ったときのばらつき | |

- 参照音声を 2〜3 種類（落ち着いた声／配信のテンション）に替えても改善しない
- 1.7B でも「声の似かた」が 3 未満

この両方に当てはまるときだけ、追加学習（ファインチューニング）を検討する。
公式のファインチューニング手順は CUDA（NVIDIA GPU）前提なので、M1 で動く前提にはしない。
その場合はクラウド GPU の比較と費用見積もりを先に出し、承認を得てから進める。

## ライセンス・利用上の注意

| 対象 | ライセンス | 確認状況 |
|---|---|---|
| mlx-audio | MIT | リポジトリの LICENSE で確認済み |
| mlx | MIT | Apple の公開ライセンス |
| Qwen3-TTS Base（mlx-community の 8bit 版） | Apache-2.0 | 事前調査による。HF のモデルカードは Mac 側で再確認すること |

- Apache-2.0 / MIT はどちらも商用利用可。ライセンス表示と免責の条件は守る
- クローンの対象は**本人の声に限る**。他人の声は使わない
- YouTube では、本物と見分けがつかない合成音声を使った動画に「改変・合成コンテンツ」の開示が必要になる場合がある。投稿前に最新のポリシーを確認する
- 処理はすべてローカル。音声を外部サービスへ送らない（モデルのダウンロードだけ Hugging Face に接続する）

## 既知の制約

- 長い文章は改行で区切って渡す（自動の分割は Phase 4 で検討）
- `--lang japanese` がモデルの言語一覧に無い場合は警告を出し、`auto` として扱われる
- 生成速度（リアルタイム比）とピークメモリは `history.jsonl` に残るので、0.6B と 1.7B を比べる材料にできる

## アンインストール

```bash
rm -rf ~/suzukana-voice-clone
```

`setup.sh` で入れた uv もこのフォルダ内（`.uv-bin/`）なので一緒に消える。
既存の `~/.cache/huggingface` などフォルダ外のものは使わないし、消さない。

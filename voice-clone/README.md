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
  ref.sh            参照音声の切り出し＋文字起こし下書き（scripts/make_ref.py）
  pick.sh           文ごとに似かたスコア最上位を選び、参照音声ごとに1本へつないで再生（scripts/pick_best.py）
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

切り出しと文字起こしの下書きは `ref.sh` でできる（m4a などは ffmpeg で読む）:

```bash
./ref.sh --src ~/Downloads/S001.m4a --start 0.40 --end 9.39 --name ref_a
afplay refs/ref_a.wav          # 聞きながら refs/ref_a.txt を一字一句直す
```

文字起こしには `mlx-community/Qwen3-ASR-0.6B-8bit`（Apache-2.0、1GB 前後）を使う。初回だけ y/N で確認してからダウンロードする。

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
- 文章は自動で文ごと（。！？・改行）に分けて生成し、文の間に短い無音を入れてつなぐ。40字を超える文は読点でも分ける。分けたくないときは `--no-split`
- 読みを間違える語は `dict.tsv`（`表記<TAB>読み`）に書くと、生成前に置き換わる。初期値は `錫奏 → すずかな`
- 生成ごとに「似かたスコア」（モデル内蔵の話者エンコーダで、参照音声とのコサイン類似度。1 に近いほど近い）を表示し、`history.jsonl` にも残す。数値は目安で、最終判断は耳で行う
- `--temperature 0.9,1.1 --seed 0,1,2` のようにカンマ区切りで渡すと、モデルを1回読むだけで全組み合わせを生成する（ファイル名に `_<参照名>_t<温度>_s<seed>` が付く）
- `--name` で出力名を指定。同名ファイルがあると上書きせずに止まる

出力（`outputs/`）:

| ファイル | 中身 |
|---|---|
| `<日時>_<文頭>.wav` | 生成音声（24kHz モノラル） |
| `<日時>_<文頭>_compare.wav` | 参照音声 → 無音0.7秒 → 生成音声。聞き比べ用 |
| `history.jsonl` | 1生成1行。入力文、参照音声のパスと SHA-256、モデル、バージョン、設定、生成時間、ピークメモリ、エラー内容 |

再生: `afplay outputs/xxx_compare.wav`、または Finder でクイックルック（スペースキー）。

## 試作の評価（Phase 5 の判断材料）

評価用の5文は `samples/eval_ja.txt`（あいさつ、驚き・疑問、テンション高め、数字と固有名詞、長め）。1文ずつ生成するには:

```bash
while IFS= read -r line; do
  ./run.sh --ref-audio refs/ref_b.wav --ref-text-file refs/ref_b.txt --text "$line" --temperature 1.1 --seed 0,1,2 < /dev/null
done < samples/eval_ja.txt
```

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

## 試作結果の記録

| 日付 | モデル | 参照音声 | 設定 | 似かた | 読み | 自然さ | 速度 / ピークメモリ | メモ |
|---|---|---|---|---|---|---|---|---|
| 2026-10-19 | 0.6B-Base-8bit | ref_a（S001 0.40–9.39s） | t=0.9, seed=0 | 3 | 5 | 3 | 4.5秒を14.6秒（RTF 3.2）/ 6.09GB | 抑揚にAIっぽさが残る |
| 2026-10-19 | 0.6B-Base-8bit | ref_a / ref_b（S007 0.00–6.98s）/ ref_c（S002 2.45–11.51s） | t=0.9,1.1 × seed=0,1 の12本 | – | – | – | – | **ref_b・t=1.1・seed=1 が一番本人らしい** |
| 2026-10-19 | 0.6B-Base-8bit | ref_b | t=1.1、評価5文 × seed=0,1,2 | 4 / 3 / 4 / 3 | 4※ / 5 / 5 / 5 | 4 / 3 / 2 / 2 | – | 順に あいさつ / 驚き / 数字 / 長文（テンション高めの文は未評価）。※「錫奏」を毎回すずかなとは読めない。長い文ほど自然さと似かたが落ちる |

- メモリ 8GB の M1 では 0.6B でもピーク 6GB を超えるので、1.7B は現実的でない
- 3回目の音声を分析すると、参照音声（ref_b）の声の高さの中央値は 282Hz だった。生成音声は 254〜326Hz と、文によって ±2.5 半音ほど上下にぶれていた。評価が最も低かった「数字」の文は、声が低めで抑揚の幅も狭く、間もほとんど無かった。→ 文ごとに分けて生成する、読み仮名の辞書、似かたスコアで良い seed を選ぶ、の3つを追加した

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

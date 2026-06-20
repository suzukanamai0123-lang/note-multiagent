"""
note収益化記事を作るマルチエージェントパイプライン

5つのエージェントを順番に実行し、各ステップの出力を次のエージェントの入力として渡す。
1. リサーチAI -> 2. 企画AI -> 3. ライターAI -> 4. 編集長AI -> 5. 集客AI
"""

import os
import sys
import json
from datetime import datetime

import anthropic

MODEL = "claude-sonnet-4-6"


def get_client() -> anthropic.Anthropic:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets.get("ANTHROPIC_API_KEY")
        except Exception:
            pass
    if not api_key:
        raise RuntimeError(
            "環境変数 ANTHROPIC_API_KEY が設定されていません。"
            "export ANTHROPIC_API_KEY='sk-ant-...' を実行してください。"
        )
    return anthropic.Anthropic(api_key=api_key)


def call_agent(client: anthropic.Anthropic, system_prompt: str, user_prompt: str, max_tokens: int = 4096) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return response.content[0].text


# ---------------------------------------------------------------------------
# 各エージェントの定義
# ---------------------------------------------------------------------------

def research_agent(client: anthropic.Anthropic, topic: str) -> str:
    system = (
        "あなたはnote収益化のための市場リサーチAIです。"
        "指定されたテーマについて、現在のトレンド、読者層の関心、"
        "competing noteクリエイターがよく使う切り口、検索されやすいキーワードを分析してください。"
        "出力は箇条書き中心で簡潔にまとめてください。"
    )
    user = f"テーマ: {topic}\n\nこのテーマについてトレンドと競合分析を行ってください。"
    return call_agent(client, system, user)


def planning_agent(client: anthropic.Anthropic, topic: str, research: str, user_input: str = "") -> str:
    system = (
        "あなたはnote記事の企画AIです。"
        "リサーチ結果を踏まえて、ターゲット読者像、記事のゴール（読者にどう行動してほしいか）、"
        "タイトル案3つ、見出し構成（H2/H3レベルの目次）を作成してください。"
        "noteで収益化（有料記事化・マガジン誘導・サービス誘導など）しやすい構成を意識してください。"
        "著者本人の体験談・考えが与えられた場合は、それを記事の中心軸として構成に組み込んでください。"
    )
    user = f"テーマ: {topic}\n\n# リサーチ結果\n{research}"
    if user_input:
        user += f"\n\n# 著者本人の体験談・考え（これを記事の軸にしてください）\n{user_input}"
    user += "\n\nこの情報を元に企画書を作成してください。"
    return call_agent(client, system, user)


def writer_agent(
    client: anthropic.Anthropic,
    topic: str,
    plan: str,
    user_input: str = "",
    plan_feedback: str = "",
) -> str:
    system = (
        "あなたはnote記事のライターAIです。"
        "渡された企画書（ターゲット、ゴール、構成案）に忠実に、読みやすく説得力のある記事本文を執筆してください。"
        "Markdown形式で見出しを使い、具体例や数字を交えて説得力を持たせてください。"
        "文末には軽い行動喚起（CTA）を入れてください。"
        "著者本人の体験談・考えが与えられた場合は、それを最大限活かし、実体験に基づくリアルな記述にしてください。"
        "企画書への修正指示が与えられた場合は、それを必ず反映した上で執筆してください。"
    )
    user = f"テーマ: {topic}\n\n# 企画書\n{plan}"
    if plan_feedback:
        user += f"\n\n# 企画書への修正指示（必ず反映してください）\n{plan_feedback}"
    if user_input:
        user += f"\n\n# 著者本人の体験談・考え（必ず反映してください）\n{user_input}"
    user += "\n\nこの企画書に基づいて記事本文を執筆してください。"
    return call_agent(client, system, user, max_tokens=8192)


def editor_agent(client: anthropic.Anthropic, draft: str, user_feedback: str = "") -> str:
    system = (
        "あなたはnote編集長AIです。"
        "渡された記事ドラフトを読み、誤字脱字、論理の飛躍、冗長な表現、"
        "読者にとって分かりにくい部分をチェックし、改善した最終版の記事全文を出力してください。"
        "著者からの修正指示が与えられた場合は、それを必ず反映してください。"
        "修正点の説明は不要で、修正済みの記事本文のみをMarkdownで出力してください。"
    )
    user = f"# 記事ドラフト\n{draft}"
    if user_feedback:
        user += f"\n\n# 著者からの修正指示（必ず反映してください）\n{user_feedback}"
    user += "\n\nこの記事を校正・編集し、最終版を出力してください。"
    return call_agent(client, system, user, max_tokens=8192)


def promotion_agent(client: anthropic.Anthropic, final_article: str) -> str:
    system = (
        "あなたはnote記事の集客AIです。"
        "渡された最終記事を読み、X（旧Twitter）とThreads向けの投稿案をそれぞれ3パターン作成してください。"
        "Xは140字程度、Threadsは500字程度を目安にし、それぞれ記事への興味を引くフックと、"
        "noteへの誘導を意識した文章にしてください。ハッシュタグも提案してください。"
    )
    user = f"# 最終記事\n{final_article}\n\nこの記事を宣伝するためのX・Threads投稿案を作成してください。"
    return call_agent(client, system, user)


# ---------------------------------------------------------------------------
# パイプライン本体
# ---------------------------------------------------------------------------

def ask_user_input(prompt: str) -> str:
    print(f"\n{prompt}")
    print("（複数行入力可。入力を終えたら何も入力せずEnterを押してください）")
    lines = []
    while True:
        line = input()
        if line == "":
            break
        lines.append(line)
    return "\n".join(lines)


def run_pipeline(topic: str, output_dir: str = "output", interactive: bool = True) -> dict:
    client = get_client()
    results = {}

    print(f"[1/5] リサーチAI 実行中... テーマ: {topic}")
    results["research"] = research_agent(client, topic)
    print("\n----- リサーチ結果 -----")
    print(results["research"])

    user_experience = ""
    if interactive:
        user_experience = ask_user_input(
            "この内容を踏まえて、あなた自身の体験談や考え・盛り込みたい視点があれば入力してください（なければそのままEnter）："
        )
    results["user_experience"] = user_experience

    print("\n[2/5] 企画AI 実行中...")
    results["plan"] = planning_agent(client, topic, results["research"], user_experience)
    print("\n----- 企画書 -----")
    print(results["plan"])

    plan_feedback = ""
    if interactive:
        plan_feedback = ask_user_input(
            "この企画書について、修正してほしい点（ターゲット・タイトル・構成など）があれば入力してください（なければそのままEnter）："
        )
    results["plan_feedback"] = plan_feedback

    print("\n[3/5] ライターAI 実行中...")
    results["draft"] = writer_agent(client, topic, results["plan"], user_experience, plan_feedback)
    print("\n----- 記事ドラフト -----")
    print(results["draft"])

    user_feedback = ""
    if interactive:
        user_feedback = ask_user_input(
            "このドラフトについて、修正してほしい点や追加したい体験談があれば入力してください（なければそのままEnter）："
        )
    results["user_feedback"] = user_feedback

    print("\n[4/5] 編集長AI 実行中...")
    results["final_article"] = editor_agent(client, results["draft"], user_feedback)

    print("[5/5] 集客AI 実行中...")
    results["promotion"] = promotion_agent(client, results["final_article"])

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = os.path.join(output_dir, f"{timestamp}_{topic[:20]}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    article_path = os.path.join(output_dir, f"{timestamp}_article.md")
    with open(article_path, "w", encoding="utf-8") as f:
        f.write(results["final_article"])

    print(f"\n完了しました。")
    print(f"全工程の結果: {out_path}")
    print(f"記事本文のみ: {article_path}")

    return results


def main():
    if len(sys.argv) < 2:
        print("使い方: python note_pipeline.py \"記事のテーマ\"")
        sys.exit(1)
    topic = sys.argv[1]
    run_pipeline(topic)


if __name__ == "__main__":
    main()

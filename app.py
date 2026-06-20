"""
note収益化記事マルチエージェントパイプライン - Streamlit版

ターミナルでの input() を使わず、ブラウザ上で
リサーチ結果・企画書・ドラフトを確認しながら体験談や修正指示を入力できる。

起動方法:
    streamlit run app.py
"""

import os
import streamlit as st

from note_pipeline import (
    get_client,
    research_agent,
    planning_agent,
    writer_agent,
    editor_agent,
    promotion_agent,
)
import history_store

st.set_page_config(page_title="note収益化記事AIパイプライン", layout="wide")
st.title("note収益化記事マルチエージェントパイプライン")

if "step" not in st.session_state:
    st.session_state.step = 0
    st.session_state.data = {}
if "viewing_article_id" not in st.session_state:
    st.session_state.viewing_article_id = None

api_key_set = bool(os.environ.get("ANTHROPIC_API_KEY")) or bool(st.secrets.get("ANTHROPIC_API_KEY", None))
if not api_key_set:
    st.error("ANTHROPIC_API_KEY が設定されていません。環境変数、またはStreamlit Cloudのsecretsで設定してください。")
    st.stop()


def reset():
    st.session_state.step = 0
    st.session_state.data = {}
    st.session_state.viewing_article_id = None


with st.sidebar:
    st.button("新しい記事を書く", on_click=reset)
    st.divider()
    st.subheader("過去の記事")
    articles = history_store.list_articles()
    if not articles:
        st.caption("まだ保存された記事はありません")
    for article in articles:
        label = f"{article['created_at'][:16]}　{article['topic']}"
        if st.button(label, key=f"history_{article['id']}", use_container_width=True):
            st.session_state.viewing_article_id = article["id"]
            st.session_state.step = -1
            st.rerun()

# --- 過去記事の表示モード ---
if st.session_state.step == -1 and st.session_state.viewing_article_id is not None:
    article = history_store.get_article(st.session_state.viewing_article_id)
    st.subheader(f"📄 {article['topic']}（{article['created_at']}）")
    st.markdown(article["final_article"])
    st.download_button(
        "記事をMarkdownでダウンロード",
        article["final_article"],
        file_name=f"{article['topic']}_article.md",
    )
    st.subheader("X・Threads 投稿案")
    st.markdown(article["promotion"])
    if st.button("この記事を削除"):
        history_store.delete_article(st.session_state.viewing_article_id)
        reset()
        st.rerun()
    st.stop()

# --- Step 0: テーマ入力 ---
if st.session_state.step == 0:
    topic = st.text_input("記事のテーマを入力してください", value=st.session_state.data.get("topic", ""))
    if st.button("リサーチ開始", disabled=not topic):
        st.session_state.data["topic"] = topic
        with st.spinner("リサーチAI 実行中..."):
            client = get_client()
            st.session_state.data["research"] = research_agent(client, topic)
        st.session_state.step = 1
        st.rerun()

# --- Step 1: リサーチ結果 -> 体験談入力 ---
if st.session_state.step == 1:
    st.subheader("① リサーチ結果")
    st.markdown(st.session_state.data["research"])
    st.divider()
    user_experience = st.text_area(
        "この内容を踏まえて、あなた自身の体験談や考え・盛り込みたい視点があれば入力してください（任意）",
        height=150,
        key="user_experience_input",
    )
    if st.button("企画AIに進む"):
        st.session_state.data["user_experience"] = user_experience
        with st.spinner("企画AI 実行中..."):
            client = get_client()
            st.session_state.data["plan"] = planning_agent(
                client,
                st.session_state.data["topic"],
                st.session_state.data["research"],
                user_experience,
            )
        st.session_state.step = 2
        st.rerun()

# --- Step 2: 企画書 -> 修正指示入力 ---
if st.session_state.step == 2:
    st.subheader("① リサーチ結果")
    with st.expander("内容を表示"):
        st.markdown(st.session_state.data["research"])

    st.subheader("② 企画書")
    st.markdown(st.session_state.data["plan"])
    st.divider()
    plan_feedback = st.text_area(
        "この企画書について、修正してほしい点（ターゲット・タイトル・構成など）があれば入力してください（任意）",
        height=150,
        key="plan_feedback_input",
    )
    if st.button("ライターAIに進む"):
        st.session_state.data["plan_feedback"] = plan_feedback
        with st.spinner("ライターAI 実行中..."):
            client = get_client()
            st.session_state.data["draft"] = writer_agent(
                client,
                st.session_state.data["topic"],
                st.session_state.data["plan"],
                st.session_state.data["user_experience"],
                plan_feedback,
            )
        st.session_state.step = 3
        st.rerun()

# --- Step 3: ドラフト -> 修正指示入力 ---
if st.session_state.step == 3:
    st.subheader("② 企画書")
    with st.expander("内容を表示"):
        st.markdown(st.session_state.data["plan"])

    st.subheader("③ 記事ドラフト")
    st.markdown(st.session_state.data["draft"])
    st.divider()
    draft_feedback = st.text_area(
        "このドラフトについて、修正してほしい点や追加したい体験談があれば入力してください（任意）",
        height=150,
        key="draft_feedback_input",
    )
    if st.button("編集長AI・集客AIに進む"):
        st.session_state.data["draft_feedback"] = draft_feedback
        with st.spinner("編集長AI 実行中..."):
            client = get_client()
            st.session_state.data["final_article"] = editor_agent(
                client, st.session_state.data["draft"], draft_feedback
            )
        with st.spinner("集客AI 実行中..."):
            st.session_state.data["promotion"] = promotion_agent(
                client, st.session_state.data["final_article"]
            )
        st.session_state.step = 4
        st.rerun()

# --- Step 4: 最終結果 ---
if st.session_state.step == 4:
    if not st.session_state.data.get("saved"):
        history_store.save_article(
            st.session_state.data["topic"],
            st.session_state.data["final_article"],
            st.session_state.data["promotion"],
        )
        st.session_state.data["saved"] = True

    st.subheader("④ 最終記事")
    st.markdown(st.session_state.data["final_article"])
    st.download_button(
        "記事をMarkdownでダウンロード",
        st.session_state.data["final_article"],
        file_name=f"{st.session_state.data['topic']}_article.md",
    )

    st.subheader("⑤ X・Threads 投稿案")
    st.markdown(st.session_state.data["promotion"])
    st.success("この記事は自動的に履歴に保存されました。サイドバーから後で見返せます。")

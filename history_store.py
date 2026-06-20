"""過去に生成した記事を保存・一覧表示するためのSQLiteストレージ"""

import sqlite3
from datetime import datetime

DB_PATH = "history.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            final_article TEXT NOT NULL,
            promotion TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    return conn


def save_article(topic: str, final_article: str, promotion: str) -> int:
    conn = _connect()
    cursor = conn.execute(
        "INSERT INTO articles (topic, final_article, promotion, created_at) VALUES (?, ?, ?, ?)",
        (topic, final_article, promotion, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    article_id = cursor.lastrowid
    conn.close()
    return article_id


def list_articles() -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT id, topic, created_at FROM articles ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [{"id": r[0], "topic": r[1], "created_at": r[2]} for r in rows]


def get_article(article_id: int) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT topic, final_article, promotion, created_at FROM articles WHERE id = ?",
        (article_id,),
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"topic": row[0], "final_article": row[1], "promotion": row[2], "created_at": row[3]}


def delete_article(article_id: int) -> None:
    conn = _connect()
    conn.execute("DELETE FROM articles WHERE id = ?", (article_id,))
    conn.commit()
    conn.close()

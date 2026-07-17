"""
高分子材料原料知识库 - 数据库层
"""
import sqlite3
import datetime
from typing import List, Optional
import bcrypt
from config import SQLITE_DB_PATH

DB_PATH = str(SQLITE_DB_PATH)


def get_db():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """初始化数据库表"""
    conn = get_db()
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL,
            title TEXT,
            manufacturer TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            material_types TEXT DEFAULT '[]',
            function_tags TEXT DEFAULT '[]',
            file_type TEXT,
            file_size INTEGER DEFAULT 0,
            upload_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            content_text TEXT DEFAULT '',
            content_zh TEXT DEFAULT '',
            tds_data TEXT DEFAULT '{}',
            language TEXT DEFAULT 'zh',
            status TEXT DEFAULT 'active',
            checksum TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_docs_status ON documents(status);
        CREATE INDEX IF NOT EXISTS idx_docs_upload_time ON documents(upload_time);

        CREATE TABLE IF NOT EXISTS comparisons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            doc_ids TEXT NOT NULL,
            created_by TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()


def get_user_by_username(username: str) -> Optional[dict]:
    """根据用户名获取用户"""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return dict(row) if row else None


def create_user(username: str, password: str, is_admin: bool = False) -> int:
    """创建用户"""
    conn = get_db()
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    cursor = conn.execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?, ?, ?)",
        (username, password_hash, 1 if is_admin else 0)
    )
    conn.commit()
    user_id = cursor.lastrowid
    conn.close()
    return user_id


def verify_password(username: str, password: str) -> Optional[dict]:
    """验证密码"""
    user = get_user_by_username(username)
    if not user:
        return None
    if bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        return user
    return None


def has_admin() -> bool:
    """检查是否已有管理员"""
    conn = get_db()
    row = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE is_admin = 1").fetchone()
    conn.close()
    return row['cnt'] > 0


def add_document(filename: str, title: str, manufacturer: str = "", summary: str = "",
                 material_types: List[str] = None, function_tags: List[str] = None,
                 file_type: str = "", file_size: int = 0, content_text: str = "",
                 content_zh: str = "", tds_data: dict = None, language: str = "zh",
                 checksum: str = "") -> int:
    """添加文档"""
    import json
    conn = get_db()
    cursor = conn.execute(
        """INSERT INTO documents
           (filename, title, manufacturer, summary, material_types, function_tags,
            file_type, file_size, content_text, content_zh, tds_data, language, checksum)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (filename, title, manufacturer, summary,
         json.dumps(material_types or [], ensure_ascii=False),
         json.dumps(function_tags or [], ensure_ascii=False),
         file_type, file_size, content_text, content_zh,
         json.dumps(tds_data or {}, ensure_ascii=False),
         language, checksum)
    )
    conn.commit()
    doc_id = cursor.lastrowid
    conn.close()
    return doc_id


def get_document(doc_id: int) -> Optional[dict]:
    """获取单个文档"""
    import json
    conn = get_db()
    row = conn.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
    conn.close()
    if not row:
        return None
    doc = dict(row)
    doc['material_types'] = json.loads(doc.get('material_types', '[]'))
    doc['function_tags'] = json.loads(doc.get('function_tags', '[]'))
    doc['tds_data'] = json.loads(doc.get('tds_data', '{}'))
    return doc


def list_documents(status: str = "active", material_type: str = None,
                   function_tag: str = None, sort_by: str = "upload_time",
                   order: str = "DESC") -> List[dict]:
    """列出文档"""
    import json
    conn = get_db()

    query = "SELECT * FROM documents WHERE status = ?"
    params = [status]

    if material_type:
        query += " AND material_types LIKE ?"
        params.append(f'%"{material_type}"%')

    if function_tag:
        query += " AND function_tags LIKE ?"
        params.append(f'%"{function_tag}"%')

    order_col = "upload_time" if sort_by == "upload_time" else "title"
    order_dir = "DESC" if order == "DESC" else "ASC"
    query += f" ORDER BY {order_col} {order_dir}"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    docs = []
    for row in rows:
        doc = dict(row)
        doc['material_types'] = json.loads(doc.get('material_types', '[]'))
        doc['function_tags'] = json.loads(doc.get('function_tags', '[]'))
        doc['tds_data'] = json.loads(doc.get('tds_data', '{}'))
        docs.append(doc)

    return docs


def update_document(doc_id: int, **kwargs) -> bool:
    """更新文档"""
    import json
    conn = get_db()

    allowed = {'title', 'summary', 'material_types', 'function_tags', 'status', 'content_text'}
    updates = {}
    for k, v in kwargs.items():
        if k in allowed:
            if k in ('material_types', 'function_tags') and isinstance(v, list):
                updates[k] = json.dumps(v, ensure_ascii=False)
            else:
                updates[k] = v

    if not updates:
        conn.close()
        return False

    updates['updated_at'] = datetime.datetime.now().isoformat()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [doc_id]

    conn.execute(f"UPDATE documents SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    return True


def delete_document(doc_id: int) -> bool:
    """删除文档（软删除）"""
    conn = get_db()
    conn.execute(
        "UPDATE documents SET status = 'deleted', updated_at = ? WHERE id = ?",
        (datetime.datetime.now().isoformat(), doc_id)
    )
    affected = conn.total_changes
    conn.commit()
    conn.close()
    return affected > 0


def get_doc_by_checksum(checksum: str) -> Optional[dict]:
    """根据 checksum 查找文档"""
    conn = get_db()
    row = conn.execute("SELECT * FROM documents WHERE checksum = ? AND status != 'deleted'",
                       (checksum,)).fetchone()
    conn.close()
    if row:
        import json
        doc = dict(row)
        doc['material_types'] = json.loads(doc.get('material_types', '[]'))
        doc['function_tags'] = json.loads(doc.get('function_tags', '[]'))
        return doc
    return None


# --- 对比功能 ---

def add_comparison(name: str, doc_ids: List[int], created_by: str = "") -> int:
    """创建对比"""
    import json
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO comparisons (name, doc_ids, created_by) VALUES (?, ?, ?)",
        (name, json.dumps(doc_ids, ensure_ascii=False), created_by)
    )
    conn.commit()
    comp_id = cursor.lastrowid
    conn.close()
    return comp_id


def get_comparison(comp_id: int) -> Optional[dict]:
    """获取单个对比"""
    import json
    conn = get_db()
    row = conn.execute("SELECT * FROM comparisons WHERE id = ?", (comp_id,)).fetchone()
    conn.close()
    if not row:
        return None
    comp = dict(row)
    comp['doc_ids'] = json.loads(comp.get('doc_ids', '[]'))
    return comp


def list_comparisons() -> List[dict]:
    """列出所有对比"""
    import json
    conn = get_db()
    rows = conn.execute("SELECT * FROM comparisons ORDER BY updated_at DESC").fetchall()
    conn.close()
    comps = []
    for row in rows:
        comp = dict(row)
        comp['doc_ids'] = json.loads(comp.get('doc_ids', '[]'))
        comps.append(comp)
    return comps


def delete_comparison(comp_id: int) -> bool:
    """删除对比"""
    conn = get_db()
    conn.execute("DELETE FROM comparisons WHERE id = ?", (comp_id,))
    affected = conn.total_changes
    conn.commit()
    conn.close()
    return affected > 0

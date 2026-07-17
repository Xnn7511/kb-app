"""
高分子材料原料知识库 - FastAPI 主应用
"""
import os
import sys
import json
import shutil
import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import jwt

# 添加后端路径
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    SECRET_KEY, ALGORITHM, UPLOAD_DIR, ALLOWED_EXTENSIONS,
    MATERIAL_TYPES, FUNCTION_TAGS
)
from database import (
    init_db, get_user_by_username, create_user, verify_password,
    has_admin, add_document, get_document, list_documents,
    update_document, delete_document, get_doc_by_checksum,
    add_comparison, get_comparison, list_comparisons, delete_comparison
)
from file_parser import parse_file, compute_checksum
from rag_engine import rag_engine

app = FastAPI(
    title="高分子材料原料知识库",
    description="Polymer Material Knowledge Base",
    version="1.0.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer(auto_error=False)

# 初始化数据库
init_db()


# ============ 认证相关 ============

def create_token(user_id: int, username: str, is_admin: bool) -> str:
    """创建 JWT Token"""
    payload = {
        "user_id": user_id,
        "username": username,
        "is_admin": is_admin,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=480),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解码 JWT Token"""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """获取当前用户（可选认证）"""
    if not credentials:
        return None
    return decode_token(credentials.credentials)


async def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """要求管理员权限"""
    if not credentials:
        raise HTTPException(status_code=401, detail="需要登录")
    user = decode_token(credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


# ============ 认证接口 ============

@app.get("/api/auth/status")
async def auth_status():
    """检查认证状态（是否有管理员）"""
    return {"has_admin": has_admin()}


@app.post("/api/auth/init-admin")
async def init_admin(data: dict):
    """初始化管理员（仅当没有管理员时可用）"""
    if has_admin():
        raise HTTPException(status_code=400, detail="管理员已存在，不能重复初始化")

    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if len(username) < 2 or len(password) < 6:
        raise HTTPException(status_code=400, detail="用户名至少2位，密码至少6位")

    user_id = create_user(username, password, is_admin=True)
    token = create_token(user_id, username, True)

    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": True,
        "message": "管理员创建成功"
    }


@app.post("/api/auth/login")
async def login(data: dict):
    """用户登录"""
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    user = verify_password(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_token(user['id'], user['username'], bool(user['is_admin']))
    return {
        "access_token": token,
        "token_type": "bearer",
        "is_admin": bool(user['is_admin']),
    }


# ============ 标签配置 ============

@app.get("/api/tags")
async def get_tags():
    """获取所有可用标签"""
    return {
        "material_types": MATERIAL_TYPES,
        "function_tags": FUNCTION_TAGS,
    }


# ============ 文档管理 ============

@app.get("/api/documents")
async def api_list_documents(
    status: str = "active",
    material_type: Optional[str] = None,
    function_tag: Optional[str] = None,
    sort_by: str = "upload_time",
    order: str = "DESC",
    page: int = 1,
    page_size: int = 20,
):
    """列出文档"""
    docs = list_documents(status, material_type, function_tag, sort_by, order)

    # 简单分页
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    page_docs = docs[start:end]

    # 不返回完整文本内容
    for doc in page_docs:
        doc['content_preview'] = doc.get('content_text', '')[:500]
        doc.pop('content_text', None)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": page_docs,
    }


@app.get("/api/documents/{doc_id}")
async def api_get_document(doc_id: int):
    """获取单个文档详情"""
    doc = get_document(doc_id)
    if not doc or doc.get('status') == 'deleted':
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@app.post("/api/documents/upload")
async def api_upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(require_admin),
):
    """上传文档（管理员）"""
    # 检查文件类型
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型: {ext}。支持的类型: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # 保存文件
    os.makedirs(str(UPLOAD_DIR), exist_ok=True)
    safe_filename = file.filename.replace("/", "_").replace("\\", "_")
    filepath = UPLOAD_DIR / safe_filename

    # 如果文件已存在，添加时间戳
    if filepath.exists():
        stem = Path(safe_filename).stem
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        safe_filename = f"{stem}_{ts}{ext}"
        filepath = UPLOAD_DIR / safe_filename

    content = await file.read()
    with open(filepath, 'wb') as f:
        f.write(content)

    # 计算 checksum
    checksum = compute_checksum(str(filepath))

    # 检查是否已存在
    existing = get_doc_by_checksum(checksum)
    if existing:
        # 删除重复文件
        os.remove(filepath)
        return {
            "message": "文件已存在，跳过上传",
            "document_id": existing['id'],
            "duplicate": True,
        }

    # 解析文件
    text_content, file_type = parse_file(str(filepath))

    # AI 自动分类
    title = Path(safe_filename).stem
    metadata = rag_engine.auto_classify(title, text_content)

    # 保存到数据库
    doc_id = add_document(
        filename=safe_filename,
        title=metadata.get("title", title),
        summary=metadata.get("summary", text_content[:200]),
        material_types=metadata.get("material_types", []),
        function_tags=metadata.get("function_tags", []),
        file_type=file_type,
        file_size=len(content),
        content_text=text_content,
        checksum=checksum,
    )

    # 索引到向量数据库
    try:
        rag_engine.index_document(doc_id, text_content)
    except Exception as e:
        # 索引失败不影响上传成功
        pass

    return {
        "message": "上传成功",
        "document_id": doc_id,
        "filename": safe_filename,
        "title": metadata.get("title", title),
        "summary": metadata.get("summary", "")[:200],
        "material_types": metadata.get("material_types", []),
        "function_tags": metadata.get("function_tags", []),
        "file_type": file_type,
        "file_size": len(content),
    }


@app.put("/api/documents/{doc_id}")
async def api_update_document(
    doc_id: int,
    data: dict,
    user: dict = Depends(require_admin),
):
    """更新文档（管理员）"""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    success = update_document(doc_id, **data)
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")

    return {"message": "更新成功", "document_id": doc_id}


@app.delete("/api/documents/{doc_id}")
async def api_delete_document(
    doc_id: int,
    user: dict = Depends(require_admin),
):
    """删除文档（管理员，软删除）"""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    delete_document(doc_id)

    # 从向量库中移除
    try:
        rag_engine.remove_document(doc_id)
    except Exception:
        pass

    return {"message": "删除成功", "document_id": doc_id}


@app.get("/api/documents/{doc_id}/download")
async def api_download_document(doc_id: int):
    """下载原始文件"""
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")

    filepath = UPLOAD_DIR / doc['filename']
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    return FileResponse(str(filepath), filename=doc['filename'])


# ============ 智能检索 ============

@app.post("/api/search")
async def api_search(data: dict):
    """语义检索"""
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    top_k = data.get("top_k", 5)
    filter_material = data.get("filter_material")
    filter_function = data.get("filter_function")

    results = rag_engine.search(
        query, top_k=top_k,
        filter_material=filter_material,
        filter_function=filter_function,
    )

    return {"query": query, "results": results, "total": len(results)}


@app.post("/api/chat")
async def api_chat(data: dict):
    """智能对话"""
    query = data.get("query", "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")

    history = data.get("history", [])
    top_k = data.get("top_k", 5)

    answer, references = rag_engine.generate_answer(query, history, top_k)

    return {
        "query": query,
        "answer": answer,
        "references": references,
    }


# ============ 实验方案 ============

@app.post("/api/experiment")
async def api_experiment(data: dict):
    """生成实验方案"""
    goal = data.get("goal", "").strip()
    if not goal:
        raise HTTPException(status_code=400, detail="实验目标不能为空")

    constraints = data.get("constraints", "").strip()

    plan, review_notes, references = rag_engine.generate_experiment_plan(goal, constraints)

    return {
        "goal": goal,
        "plan": plan,
        "review_notes": review_notes,
        "references": references,
    }


# ============ 对比功能 ============

@app.post("/api/comparisons")
async def api_create_comparison(data: dict):
    """创建对比"""
    name = data.get("name", "").strip()
    doc_ids = data.get("doc_ids", [])
    if not name:
        raise HTTPException(status_code=400, detail="对比名称不能为空")
    if not doc_ids or len(doc_ids) < 2:
        raise HTTPException(status_code=400, detail="至少需要选择 2 种材料进行对比")
    if len(doc_ids) > 4:
        raise HTTPException(status_code=400, detail="最多只能选择 4 种材料进行对比")
    comp_id = add_comparison(name, doc_ids)
    return {"id": comp_id, "name": name, "doc_ids": doc_ids}


@app.get("/api/comparisons")
async def api_list_comparisons():
    """列出所有对比"""
    comps = list_comparisons()
    return {"comparisons": comps}


@app.get("/api/comparisons/{comp_id}")
async def api_get_comparison(comp_id: int):
    """获取对比详情"""
    comp = get_comparison(comp_id)
    if not comp:
        raise HTTPException(status_code=404, detail="对比不存在")
    # 获取每个文档的详情
    documents = []
    for doc_id in comp.get("doc_ids", []):
        doc = get_document(doc_id)
        if doc:
            documents.append(doc)
    return {
        "id": comp["id"],
        "name": comp["name"],
        "created_by": comp.get("created_by", ""),
        "created_at": comp.get("created_at", ""),
        "documents": documents,
    }


@app.delete("/api/comparisons/{comp_id}")
async def api_delete_comparison(comp_id: int):
    """删除对比"""
    if delete_comparison(comp_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="对比不存在")


# ============ 健康检查 ============

@app.get("/api/health")
async def health_check():
    """健康检查"""
    return {
        "status": "ok",
        "version": "1.0.0",
        "timestamp": datetime.datetime.now().isoformat(),
    }


# ============ 静态文件服务 ============

# 挂载前端静态文件
frontend_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if frontend_dir.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dir / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """服务前端页面"""
        file_path = frontend_dir / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dir / "index.html"))
else:
    @app.get("/")
    async def root():
        return {"message": "高分子材料原料知识库 API", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

"""
高分子材料原料知识库 - 数据模型
"""
import datetime
from pydantic import BaseModel, Field
from typing import List, Optional


class UserModel(BaseModel):
    """用户模型"""
    id: int
    username: str
    is_admin: bool = False
    created_at: datetime.datetime


class UserCreate(BaseModel):
    """创建用户"""
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class UserLogin(BaseModel):
    """用户登录"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    is_admin: bool = False


class DocumentModel(BaseModel):
    """文档模型"""
    id: int
    filename: str
    title: str
    summary: str = ""
    material_types: List[str] = []
    function_tags: List[str] = []
    file_type: str
    file_size: int
    upload_time: datetime.datetime
    updated_at: datetime.datetime
    content_text: str = ""
    status: str = "active"


class DocumentCreate(BaseModel):
    """创建文档"""
    title: Optional[str] = None
    material_types: Optional[List[str]] = None
    function_tags: Optional[List[str]] = None


class DocumentUpdate(BaseModel):
    """更新文档"""
    title: Optional[str] = None
    summary: Optional[str] = None
    material_types: Optional[List[str]] = None
    function_tags: Optional[List[str]] = None
    status: Optional[str] = None


class SearchQuery(BaseModel):
    """搜索查询"""
    query: str
    top_k: int = 5
    filter_material: Optional[str] = None
    filter_function: Optional[str] = None


class SearchResult(BaseModel):
    """搜索结果"""
    document_id: int
    filename: str
    title: str
    chunk_text: str
    score: float
    material_types: List[str] = []
    function_tags: List[str] = []


class ChatMessage(BaseModel):
    """对话消息"""
    role: str  # user / assistant
    content: str


class ChatRequest(BaseModel):
    """对话请求"""
    query: str
    history: List[ChatMessage] = []


class ChatResponse(BaseModel):
    """对话响应"""
    answer: str
    references: List[dict] = []


class ExperimentRequest(BaseModel):
    """实验方案请求"""
    goal: str
    constraints: Optional[str] = None


class ExperimentResponse(BaseModel):
    """实验方案响应"""
    goal: str
    plan: str
    review_notes: str
    references: List[dict] = []


class InitAdminRequest(BaseModel):
    """初始化管理员"""
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


# --- 对比功能模型 ---

class ComparisonCreate(BaseModel):
    """创建对比"""
    name: str = Field(..., min_length=1, max_length=100)
    doc_ids: List[int] = Field(..., min_length=2, max_length=4)


class ComparisonModel(BaseModel):
    """对比模型"""
    id: int
    name: str
    doc_ids: List[int]
    created_by: str = ""
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ComparisonDetail(BaseModel):
    """对比详情（含文档数据）"""
    id: int
    name: str
    created_by: str = ""
    created_at: datetime.datetime
    documents: List[dict] = []

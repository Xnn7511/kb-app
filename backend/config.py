"""
高分子材料原料知识库 - 配置模块
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 尝试加载 .env 文件（本地开发用）
env_path = BASE_DIR / "backend" / ".env"
if env_path.exists():
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip())

# 数据目录（Render 上使用 /var/data 持久卷，本地使用 data/ 目录）
PERSIST_DIR = os.environ.get("PERSIST_DIR", str(BASE_DIR / "data"))
DATA_DIR = Path(PERSIST_DIR)
CHROMA_DIR = DATA_DIR / "chroma"
UPLOAD_DIR = BASE_DIR / "uploads" / "raw"
CONFIG_DIR = DATA_DIR / "config"

# 确保目录存在
for d in [DATA_DIR, CHROMA_DIR, UPLOAD_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# 数据库配置
SQLITE_DB_PATH = DATA_DIR / "polymer_kb.db"
DATABASE_URL = f"sqlite:///{SQLITE_DB_PATH}"

# JWT 配置
SECRET_KEY = os.environ.get("SECRET_KEY", "polymer-kb-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 小时

# 向量数据库配置
CHROMA_COLLECTION_NAME = "polymer_materials"
EMBEDDING_MODEL = "BAAI/bge-large-zh-v1.5"  # SiliconFlow 嵌入模型名称

# 材料类型标签
MATERIAL_TYPES = [
    "热塑性", "热固性", "弹性体", "工程塑料", "通用塑料",
    "胶粘剂", "涂料", "橡胶", "纤维", "复合材料",
    "功能材料", "生物基材料", "其他"
]

# 功效特性标签
FUNCTION_TAGS = [
    "增强", "增韧", "阻燃", "导电", "导热", "耐磨",
    "耐候", "低翘曲", "耐高温", "耐低温", "耐化学",
    "绝缘", "抗静电", "抗菌", "抗UV", "透明",
    "轻量化", "可降解", "低VOC", "高光泽", "其他"
]

# 支持的文件类型
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".md", ".csv", ".xlsx", ".xls"}

# LLM 配置（使用环境变量或默认值）
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.openai.com/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o-mini")

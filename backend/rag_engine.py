"""
高分子材料原料知识库 - RAG 检索引擎
使用 SiliconFlow API 进行嵌入（无需本地模型），大幅减小部署体积
"""
import json
import os
from typing import List, Dict, Optional, Tuple
from pathlib import Path

from chromadb import PersistentClient
from chromadb.config import Settings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import (
    CHROMA_DIR, EMBEDDING_MODEL, CHROMA_COLLECTION_NAME,
    LLM_API_KEY, LLM_API_BASE, LLM_MODEL,
    MATERIAL_TYPES, FUNCTION_TAGS
)
from database import get_document, list_documents

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class RAGEngine:
    """RAG 检索引擎（基于 SiliconFlow API 嵌入）"""

    def __init__(self):
        self._chroma_client = None
        self._collection = None
        self._embedding_dim = 1024  # bge-large-zh-v1.5 输出维度
        # 嵌入 API 配置
        self._embedding_model_name = "BAAI/bge-large-zh-v1.5"
        self._embedding_api_url = f"{LLM_API_BASE}/embeddings"

    @property
    def chroma_client(self):
        if self._chroma_client is None:
            os.makedirs(str(CHROMA_DIR), exist_ok=True)
            self._chroma_client = PersistentClient(
                path=str(CHROMA_DIR),
                settings=Settings(anonymized_telemetry=False)
            )
        return self._chroma_client

    @property
    def collection(self):
        if self._collection is None:
            try:
                self._collection = self.chroma_client.get_collection(CHROMA_COLLECTION_NAME)
            except Exception:
                self._collection = self.chroma_client.create_collection(
                    name=CHROMA_COLLECTION_NAME,
                    metadata={"hnsw:space": "cosine"}
                )
        return self._collection

    def split_text(self, text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
        """将文本分割成块"""
        if not text or len(text) < 50:
            return [text] if text else []

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            separators=["\n\n", "\n", "。", ".", "；", ";", "，", ",", " ", ""],
            length_function=len,
        )
        chunks = splitter.split_text(text)
        return chunks

    def _truncate_text(self, text: str, max_chars: int = 1500) -> str:
        """截断文本以适配嵌入模型的 token 限制（bge-large-zh-v1.5: 512 tokens ≈ 1500 字符）"""
        if len(text) <= max_chars:
            return text
        # 尽量在句子边界截断
        truncated = text[:max_chars]
        for sep in ['。', '；', '，', '.', ';', ',', '\n', ' ']:
            last_idx = truncated.rfind(sep)
            if last_idx > max_chars * 0.7:
                return truncated[:last_idx + 1]
        return truncated

    def _call_embedding_api(self, texts: List[str]) -> List[List[float]]:
        """调用 SiliconFlow 嵌入 API"""
        import requests

        if not LLM_API_KEY:
            logger.error("LLM_API_KEY not configured, cannot generate embeddings")
            return [[0.0] * self._embedding_dim for _ in texts]

        # 截断所有文本以适配 512 token 限制
        truncated_texts = [self._truncate_text(t) for t in texts]

        try:
            # 分批处理，每批最多 20 条
            batch_size = 20
            all_embeddings = []

            for i in range(0, len(truncated_texts), batch_size):
                batch = truncated_texts[i:i + batch_size]
                response = requests.post(
                    self._embedding_api_url,
                    headers={
                        "Authorization": f"Bearer {LLM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._embedding_model_name,
                        "input": batch,
                        "encoding_format": "float",
                    },
                    timeout=60,
                )
                if response.status_code == 200:
                    data = response.json()
                    for item in data.get("data", []):
                        all_embeddings.append(item["embedding"])
                else:
                    logger.error(f"Embedding API error: {response.status_code} {response.text}")
                    # 用零向量填充失败批次
                    for _ in batch:
                        all_embeddings.append([0.0] * self._embedding_dim)

            return all_embeddings
        except Exception as e:
            logger.error(f"Embedding API call failed: {e}")
            return [[0.0] * self._embedding_dim for _ in texts]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """将文本列表转换为向量"""
        if not texts:
            return []
        return self._call_embedding_api(texts)

    def embed_query(self, query: str) -> List[float]:
        """将查询转换为向量"""
        embeddings = self._call_embedding_api([query])
        return embeddings[0] if embeddings else [0.0] * self._embedding_dim

    def index_document(self, doc_id: int, content: str) -> int:
        """将文档内容索引到向量数据库"""
        if not content or len(content.strip()) < 20:
            return 0

        # 先删除该文档的旧索引
        try:
            self.collection.delete(where={"doc_id": str(doc_id)})
        except Exception:
            pass

        chunks = self.split_text(content)
        if not chunks:
            return 0

        embeddings = self.embed_texts(chunks)

        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"doc_id": str(doc_id), "chunk_idx": i, "chunk_text": chunk[:200]}
                     for i, chunk in enumerate(chunks)]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas,
        )

        logger.info(f"Indexed document {doc_id}: {len(chunks)} chunks")
        return len(chunks)

    def remove_document(self, doc_id: int):
        """从向量数据库中删除文档"""
        try:
            self.collection.delete(where={"doc_id": str(doc_id)})
            logger.info(f"Removed document {doc_id} from vector DB")
        except Exception as e:
            logger.error(f"Failed to remove doc {doc_id}: {e}")

    def search(self, query: str, top_k: int = 5,
               filter_material: str = None,
               filter_function: str = None) -> List[Dict]:
        """语义搜索"""
        query_embedding = self.embed_query(query)

        where_filter = None

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k * 2, 50),
            where=where_filter,
        )

        search_results = []
        if not results['ids'] or not results['ids'][0]:
            return []

        for i, chunk_id in enumerate(results['ids'][0]):
            doc_id_str = results['metadatas'][0][i].get('doc_id', '0')
            doc_id = int(doc_id_str)
            chunk_text = results['documents'][0][i]
            score = 1.0 - results['distances'][0][i] if results['distances'] else 0.5

            doc = get_document(doc_id)
            if not doc or doc.get('status') != 'active':
                continue

            # 应用层过滤
            if filter_material and filter_material not in doc.get('material_types', []):
                continue
            if filter_function and filter_function not in doc.get('function_tags', []):
                continue

            search_results.append({
                "document_id": doc_id,
                "filename": doc['filename'],
                "title": doc.get('title', doc['filename']),
                "chunk_text": chunk_text,
                "score": round(score, 4),
                "material_types": doc.get('material_types', []),
                "function_tags": doc.get('function_tags', []),
            })

        return search_results[:top_k]

    def generate_answer(self, query: str, history: List[Dict] = None,
                        top_k: int = 5) -> Tuple[str, List[Dict]]:
        """
        基于检索结果生成回答
        使用 LLM API 生成带有引用的回答
        """
        search_results = self.search(query, top_k=top_k)

        if not search_results:
            return ("当前知识库中未找到与您问题相关的资料。请确认您的问题是否与已上传的高分子材料资料相关，或尝试更换关键词。",
                    [])

        context_parts = []
        seen_docs = {}
        for r in search_results:
            doc_key = r['document_id']
            if doc_key not in seen_docs:
                seen_docs[doc_key] = r

        for doc_id, doc_info in seen_docs.items():
            context_parts.append(
                f"【来源：{doc_info['title']}（{doc_info['filename']}）】\n{doc_info['chunk_text']}"
            )

        context = "\n\n---\n\n".join(context_parts)

        history_text = ""
        if history:
            history_parts = []
            for msg in history[-6:]:
                role = "用户" if msg.get('role') == 'user' else "助手"
                history_parts.append(f"{role}: {msg.get('content', '')}")
            history_text = "\n".join(history_parts)

        system_prompt = """你是一个高分子材料原料知识库的智能助手。你的任务是基于提供的资料内容回答用户问题。

规则：
1. 仅基于提供的资料内容回答，不要编造信息
2. 如果资料中没有相关信息，明确告知用户"当前知识库中未找到相关信息"
3. 回答时标注引用来源，格式：【来源：文件名】
4. 使用专业但易懂的语言，适合高分子材料领域的工程师和研究人员阅读
5. 对于复杂问题，结构化回答（如分点说明）
6. 如涉及数据，保留原始数值和单位"""

        history_block = ""
        if history_text:
            history_block = "对话历史：\n" + history_text + "\n"

        user_prompt = f"""请基于以下资料内容回答用户问题。

资料内容：
{context}

{history_block}
用户问题：{query}

请提供准确、有引用的回答："""

        answer = self._call_llm(system_prompt, user_prompt)

        references = []
        for r in search_results[:top_k]:
            references.append({
                "document_id": r['document_id'],
                "filename": r['filename'],
                "title": r['title'],
                "excerpt": r['chunk_text'][:300],
                "score": r['score'],
            })

        return answer, references

    def auto_classify(self, title: str, content: str) -> Dict:
        """
        自动分类文档：识别材料类型和功效标签
        """
        text_sample = f"标题：{title}\n\n内容：{content[:3000]}"

        system_prompt = """你是一个高分子材料分类专家。请根据文档内容，判断材料类型和功效特性。

可用的材料类型标签：热塑性、热固性、弹性体、工程塑料、通用塑料、胶粘剂、涂料、橡胶、纤维、复合材料、功能材料、生物基材料、其他

可用的功效特性标签：增强、增韧、阻燃、导电、导热、耐磨、耐候、低翘曲、耐高温、耐低温、耐化学、绝缘、抗静电、抗菌、抗UV、透明、轻量化、可降解、低VOC、高光泽、其他

请以JSON格式返回，只返回JSON不要有其他内容：
{"title": "提取或生成的标题", "summary": "100字以内的摘要", "material_types": ["标签1", "标签2"], "function_tags": ["标签1", "标签2"]}"""

        result = self._call_llm(system_prompt, text_sample)

        try:
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[1]
                if result.endswith("```"):
                    result = result.rsplit("```", 1)[0]
                result = result.strip()
            metadata = json.loads(result)
            return {
                "title": metadata.get("title", title),
                "summary": metadata.get("summary", content[:200]),
                "material_types": metadata.get("material_types", []),
                "function_tags": metadata.get("function_tags", []),
            }
        except json.JSONDecodeError:
            return {
                "title": title,
                "summary": content[:200],
                "material_types": [],
                "function_tags": [],
            }

    def generate_experiment_plan(self, goal: str, constraints: str = "") -> Tuple[str, str, List[Dict]]:
        """
        生成实验方案 + 自动反审
        """
        search_query = f"实验配方 原料 工艺 {goal} {constraints}"
        kb_results = self.search(search_query, top_k=8)

        kb_context = ""
        seen = set()
        for r in kb_results:
            if r['filename'] not in seen:
                seen.add(r['filename'])
                kb_context += f"\n【知识库来源：{r['title']}（{r['filename']}）】\n{r['chunk_text']}\n"

        system_prompt = """你是一位资深高分子材料研发工程师，拥有20年以上的配方设计和工艺开发经验。
请根据用户的实验目标和参考资料，设计一份专业、可行的实验方案。

方案需要包含：
1. 实验目标与背景
2. 原料选择与配比（包含具体牌号推荐和用量范围）
3. 加工工艺（温度、转速、时间等参数）
4. 测试标准与方法
5. 预期结果与关键指标
6. 注意事项与风险提示

要求：
- 方案要具体、可操作，不要泛泛而谈
- 配比要有范围（如 15-25%），不要单一数值
- 工艺参数要符合工业实际
- 标注信息来源"""

        user_prompt = f"""实验目标：{goal}
{f"约束条件：{constraints}" if constraints else ""}

知识库参考资料：
{kb_context if kb_context else "（知识库中暂无直接相关资料，请基于专业知识给出方案）"}

请设计实验方案："""

        draft_plan = self._call_llm(system_prompt, user_prompt, temperature=0.5)

        review_system = """你是一位资深高分子材料专家和质量审核人。请对以下实验方案进行严格审查。

审查要点：
1. 组分相容性：各原料之间是否存在相容性问题？
2. 加工窗口：推荐的加工温度、时间是否合理？是否在原料的热稳定范围内？
3. 安全风险：是否存在分解、释放有害气体、设备腐蚀等风险？
4. 理论矛盾：方案中的结论是否与高分子科学基本原理矛盾？
5. 数据准确性：引用的数据是否合理？
6. 可操作性：实验室/工厂是否具备执行条件？

请输出以下格式：

## 审查意见
（逐条列出发现的问题）

## 修正后的方案
（将原方案修正后的完整版本）

## 修正说明
（说明做了哪些关键修改及原因）"""

        review_result = self._call_llm(review_system, f"请审查以下实验方案：\n\n{draft_plan}")

        plan = review_result
        review_notes = review_result

        if "## 修正后的方案" in review_result:
            parts = review_result.split("## 修正后的方案")
            if len(parts) >= 2:
                review_notes = parts[0].strip()
                plan_part = "## 修正后的方案" + parts[1]
                if "## 修正说明" in plan_part:
                    plan_parts = plan_part.split("## 修正说明")
                    plan = plan_parts[0].strip()
                    review_notes = review_notes + "\n\n## 修正说明" + plan_parts[1]
                else:
                    plan = plan_part.strip()

        references = []
        for r in kb_results[:8]:
            references.append({
                "document_id": r['document_id'],
                "filename": r['filename'],
                "title": r['title'],
                "excerpt": r['chunk_text'][:200],
            })

        return plan, review_notes, references

    def _call_llm(self, system_prompt: str, user_prompt: str,
                  temperature: float = 0.3) -> str:
        """调用 LLM API"""
        import requests

        if not LLM_API_KEY:
            return self._local_fallback(system_prompt, user_prompt)

        try:
            response = requests.post(
                f"{LLM_API_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": temperature,
                    "max_tokens": 4096,
                },
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
            return data['choices'][0]['message']['content']
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            return self._local_fallback(system_prompt, user_prompt)

    def _local_fallback(self, system_prompt: str, user_prompt: str) -> str:
        """当 LLM API 不可用时的本地回退"""
        return """⚠️ LLM 服务暂不可用。

请检查 API 配置（LLM_API_KEY, LLM_API_BASE 环境变量）。

如果您已配置 API Key，可能是网络或配额问题，请稍后重试。

当前知识库检索功能（语义搜索）仍可正常使用。"""


# 全局单例
rag_engine = RAGEngine()

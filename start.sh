#!/bin/bash
# 高分子材料原料知识库 - 启动脚本
set -e

PROJECT_DIR="/workspace/polymer-kb"
cd "$PROJECT_DIR"

echo "================================================"
echo "  高分子材料原料知识库 PolymerKB v1.0"
echo "================================================"
echo ""

# 设置环境变量（如果未设置）
export LLM_API_KEY="${LLM_API_KEY:-}"
export LLM_API_BASE="${LLM_API_BASE:-https://api.openai.com/v1}"
export LLM_MODEL="${LLM_MODEL:-gpt-4o-mini}"

# 检查 LLM 配置
if [ -z "$LLM_API_KEY" ]; then
    echo "⚠️  警告：未设置 LLM_API_KEY 环境变量"
    echo "   智能问答和实验方案功能将受限"
    echo "   请设置：export LLM_API_KEY=your-api-key"
    echo ""
fi

# 确保上传目录存在
mkdir -p uploads/raw

# 启动后端服务
echo "🚀 启动知识库服务..."
cd backend
python3.11 main.py

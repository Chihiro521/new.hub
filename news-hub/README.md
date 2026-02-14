# News Hub

🌸 一个现代化的新闻聚合平台，支持多源采集、智能搜索和个性化阅读。

## 🚀 快速开始

### 环境要求

- Python 3.10+
- MongoDB 5.0+
- Elasticsearch 8.x (支持向量检索)
- Node.js 18+ (前端)

### 后端安装

```bash
# 激活 Conda 环境
conda activate news-hub

# 安装依赖
cd backend
pip install -r requirements.txt

# 复制环境配置
copy .env.example .env

# 启动开发服务器
python -m uvicorn app.main:app --reload --port 8000
```

### Elasticsearch 安装

参见 `elasticsearch/README.md`

### 前端安装

```bash
cd frontend
npm install
npm run dev
```

## 📁 项目结构

```
news-hub/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── api/v1/          # API 路由
│   │   ├── core/            # 配置、安全、依赖
│   │   ├── db/              # 数据库连接
│   │   ├── schemas/         # Pydantic 模型
│   │   ├── services/        # 业务逻辑
│   │   └── main.py          # 应用入口
│   ├── scrapy_project/      # Scrapy 爬虫
│   └── tests/               # 单元测试
├── frontend/                # Vue 3 前端
├── docs/                    # 文档
│   └── progress/            # 进度报告
├── elasticsearch/           # ES 配置和脚本
└── configs/                 # 源配置文件
```

## 🔧 技术栈

### 后端
- **FastAPI** - 高性能 Web 框架
- **MongoDB + Motor** - 异步 NoSQL 数据库
- **Elasticsearch** - 全文搜索 + 向量检索
- **Scrapy** - 网页爬虫框架
- **Sentence-Transformers** - 文本向量化
- **Jieba** - 中文分词

### 前端
- **Vue 3** + TypeScript
- **Vite** - 构建工具
- **Pinia** - 状态管理

## 📋 API 文档

启动后端后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 📄 License

MIT

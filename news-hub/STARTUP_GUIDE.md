# News Hub 启动指南

## 🚀 快速启动

### 一键启动所有组件

```powershell
.\start.ps1
```

### 灵活启动

```powershell
# 只启动后端
.\start.ps1 -Backend

# 只启动前端
.\start.ps1 -Frontend

# 只启动 Elasticsearch
.\start.ps1 -Elasticsearch

# 启动后端和前端（不启动 Elasticsearch）
.\start.ps1 -Backend -Frontend

# 查看帮助
.\start.ps1 -Help
```

## 🛑 停止服务

### 推荐方式
- **后端和前端**: 直接关闭对应的 PowerShell 窗口即可
- **Elasticsearch**: 使用停止脚本

```powershell
# 停止 Elasticsearch
.\stop.ps1

# 停止所有组件
.\stop.ps1 -All
```

## 📍 访问地址

- **前端**: http://localhost:5173
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **Elasticsearch**: http://localhost:9200

## ⚙️ 前置要求

### 必需服务
- **MongoDB** (端口 27017) - 必须手动启动
- **Python 3.10+** with conda environment `news-hub`
- **Node.js 18+**

### 可选服务
- **Elasticsearch 8.x** (端口 9200) - 启动脚本会自动启动

## 🔧 启动脚本说明

启动脚本会自动：
1. ✅ 检查 MongoDB 是否运行（后端必需）
2. ✅ 检测端口占用，避免重复启动
3. ✅ 自动激活 `news-hub` conda 环境
4. ✅ 在独立窗口中启动各个组件
5. ✅ 显示所有访问地址

## 🐛 故障排查

### MongoDB 未运行
```
[错误] MongoDB 未运行！
```
**解决方案**: 启动 MongoDB 服务

### 端口被占用
如果端口 8000 或 5173 被占用，脚本会提示已运行。

查看端口占用：
```powershell
netstat -ano | findstr ":8000"
netstat -ano | findstr ":5173"
```

### 依赖未安装
启动脚本会自动检查并安装前端依赖。

如需手动安装：

**后端**:
```powershell
cd backend
pip install -r requirements.txt
```

**前端**:
```powershell
cd frontend
npm install
```

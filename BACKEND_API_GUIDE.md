# 后端 API 设置指南

您的三智能体系统，作为前端应用调用的 REST API 后端。

## 架构

```text
前端 (React/Vue 等)
    ↓ HTTP 请求
后端 API (FastAPI) ← 此文档
    ↓ Python 调用
LangGraph 工作流 (3 个智能体)
    ↓ API 调用
豆包 LLM (DouBao)
```

## 快速开始

### 1. 安装依赖 (仅需一次)

```bash
cd workplan-generator

python3 -m venv venv
source venv/bin/activate  # Windows 环境: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 启动 API 服务器

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**API 运行地址**: http://localhost:8000

**API 文档**: http://localhost:8000/docs (交互式 Swagger UI)

### 3. 生产环境部署

```bash
# 不使用自动重载
uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## API 接口参考 (Endpoints)

### 健康检查 (Health Check)

```bash
GET /health
```

响应：
```json
{
  "status": "healthy"
}
```

---

### 创建新会话 (Create New Session)

**启动一个工作计划生成会话**

```bash
POST /sessions
Content-Type: multipart/form-data

参数:
  - image: File (必填) - 显微镜图像文件
  - description: String (必填) - 简短的分析需求描述
```

**示例 (cURL):**
```bash
curl -X POST http://localhost:8000/sessions \
  -F "image=@microscope.png" \
  -F "description=计算 Ki67 阳性细胞的数量"
```

**示例 (JavaScript):**
```javascript
const formData = new FormData();
formData.append('image', imageFile);
formData.append('description', '计算 Ki67 阳性细胞的数量');

const response = await fetch('http://localhost:8000/sessions', {
  method: 'POST',
  body: formData
});

const data = await response.json();
console.log(data.session_id);  // 请保存这个 ID！
```

**响应:**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "clarification",
  "questions": [
    "这张图像中可以看到哪些染色或标记？"
  ]
}
```

---

### 回答澄清问题 (Answer Clarification Questions)

**回复智能体 1 (澄清者) 提出的问题**

```bash
POST /sessions/{session_id}/respond
Content-Type: application/json

请求体 (Body):
{
  "response": "DAPI 用于标记细胞核，Ki67 用于标记增殖细胞"
}
```

**示例 (JavaScript):**
```javascript
const response = await fetch(`http://localhost:8000/sessions/${sessionId}/respond`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    response: "DAPI 用于标记细胞核，Ki67 用于标记增殖细胞"
  })
});

const data = await response.json();

if (data.state === "clarification") {
  // 还有更多问题
  console.log("下一个问题:", data.questions);
} else if (data.state === "user_review") {
  // 工作计划已准备就绪！
  console.log("工作计划:", data.workplan);
}
```

**响应 (如果还有更多问题):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "clarification",
  "questions": [
    "您是想计算总细胞核的数量，还是只计算 Ki67 阳性细胞的数量？"
  ]
}
```

**响应 (如果工作计划已准备就绪):**
```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "state": "user_review",
  "workplan": {
    "experimentName": "Ki67 Cell Counting",
    "jobs": [...],
    "channels": [...],
    "targets": [...]
  },
  "review": {
    "status": "accept",
    "warnings": []
  }
}
```

---

### 获取会话状态 (Get Session Status)

**检查当前会话所处的状态**

```bash
GET /sessions/{session_id}
```

**示例 (JavaScript):**
```javascript
const response = await fetch(`http://localhost:8000/sessions/${sessionId}`);
const data = await response.json();

console.log("当前状态:", data.state);
// 可能的状态: "clarification", "generating", "reviewing", "user_review", "completed"
```

---

### 提交用户决定 (Submit User Decision)

**接受或要求重新生成工作计划**

```bash
POST /sessions/{session_id}/decision
Content-Type: application/json

请求体 (Body):
{
  "action": "accept"  // 也可以是 "restart_agent2" 或 "restart_agent1"
}
```

**操作选项 (Actions):**
- `"accept"` - 接受工作计划 (完成当前会话)
- `"restart_agent2"` - 重新生成工作计划 (从智能体 2 生成者处重新开始)
- `"restart_agent1"` - 重新开始并提出新问题 (从智能体 1 澄清者处重新开始)

**示例 (JavaScript):**
```javascript
const response = await fetch(`http://localhost:8000/sessions/${sessionId}/decision`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ action: "accept" })
});

const data = await response.json();
console.log("最终状态:", data.state);  // "completed"
```

---

### 下载最终工作计划 (Download Final Workplan)

**获取最终确定的工作计划 JSON 数据**

```bash
GET /sessions/{session_id}/workplan
```

**示例 (JavaScript):**
```javascript
const response = await fetch(`http://localhost:8000/sessions/${sessionId}/workplan`);
const workplan = await response.json();

console.log("最终工作计划:", workplan);
// 保存或使用该工作计划
```

**响应:**
```json
{
  "experimentName": "Ki67 Positive Cell Counting",
  "inputMode": "single_rgb_merged_image",
  "analysisGoal": "Count Ki67 positive cells",
  "channels": [
    {
      "channelId": "ch0",
      "channelName": "DAPI",
      "semanticRole": "nuclei_marker"
    },
    {
      "channelId": "ch1",
      "channelName": "Ki67",
      "semanticRole": "proliferation_marker"
    }
  ],
  "targets": [...],
  "jobs": [...]
}
```

---

## 完整前端工作流示例

### 示例: React 集成

```javascript
import React, { useState } from 'react';

function WorkplanGenerator() {
  const [sessionId, setSessionId] = useState(null);
  const [state, setState] = useState('idle');
  const [questions, setQuestions] = useState([]);
  const [workplan, setWorkplan] = useState(null);

  // 步骤 1: 上传图像
  const handleUpload = async (imageFile, description) => {
    const formData = new FormData();
    formData.append('image', imageFile);
    formData.append('description', description);

    const res = await fetch('http://localhost:8000/sessions', {
      method: 'POST',
      body: formData
    });

    const data = await res.json();
    setSessionId(data.session_id);
    setState(data.state);
    setQuestions(data.questions || []);
  };

  // 步骤 2: 回答问题
  const handleAnswer = async (answer) => {
    const res = await fetch(`http://localhost:8000/sessions/${sessionId}/respond`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ response: answer })
    });

    const data = await res.json();
    setState(data.state);

    if (data.state === 'clarification') {
      setQuestions(data.questions || []);
    } else if (data.state === 'user_review') {
      setWorkplan(data.workplan);
    }
  };

  // 步骤 3: 接受/拒绝工作计划
  const handleDecision = async (action) => {
    const res = await fetch(`http://localhost:8000/sessions/${sessionId}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action })
    });

    const data = await res.json();

    if (data.state === 'completed') {
      // 获取最终的工作计划
      const wpRes = await fetch(`http://localhost:8000/sessions/${sessionId}/workplan`);
      const finalWorkplan = await wpRes.json();

      console.log('最终工作计划:', finalWorkplan);
      // 保存或应用工作计划
    }
  };

  // 根据当前 state 渲染 UI...
  // ...
}
```

---

## 会话状态说明 (Session States)

| 状态 | 含义 | 用户操作 |
|-------|---------|-------------|
| `clarification` | 智能体 1 正在澄清需求并提问 | 通过 `/respond` 接口回答问题 |
| `generating` | 智能体 2 正在生成工作计划 | 无需操作，等待 (系统自动处理) |
| `reviewing` | 智能体 3 正在验证工作计划 | 无需操作，等待 (系统自动处理) |
| `user_review` | 工作计划已准备好供审查 | 通过 `/decision` 接口接受或要求重新生成 |
| `completed` | 工作计划已最终确定 | 通过 `/workplan` 接口下载数据 |

---

## CORS 跨域配置

该 API 默认已允许所有来源 (Origins) 的 CORS 请求。在生产环境中部署时，请在 `src/api/main.py` 中更新以下配置以确保安全：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["[https://your-frontend-domain.com](https://your-frontend-domain.com)"],  // 限制为您的前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 错误处理 (Error Handling)

所有的错误请求都会返回标准的 HTTP 状态码：

```json
// 400 Bad Request (错误请求)
{
  "detail": "Session not found"
}

// 500 Internal Server Error (内部服务器错误)
{
  "detail": "LLM API error: ..."
}
```

---

## 测试 API

### 交互式 Swagger UI

打开浏览器访问 http://localhost:8000/docs

点击任意接口 (Endpoint) → 点击 "Try it out" → 填写参数 → 点击 "Execute" 运行。

### Python 测试客户端

```bash
python test_client.py microscope.png "计算细胞数量"
```

这将通过命令行模拟一个完整的前端交互流程。

### cURL 示例

请参考上文中提供的各个接口的 cURL 示例。

---

## 生产环境部署

### 使用 Gunicorn (推荐)

```bash
pip install gunicorn

gunicorn src.api.main:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000
```

### 使用 Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t workplan-api .
docker run -p 8000:8000 --env-file .env workplan-api
```

---

## 环境配置

需要在 `.env` 中配置的必填项：

```bash
DOUBAO_API_KEY=your_key
DOUBAO_BASE_URL=[https://ark.cn-beijing.volces.com/api/v3](https://ark.cn-beijing.volces.com/api/v3)
DOUBAO_MODEL=ep-your-endpoint-id
```

可选项 (如果不设置，将默认使用内存/本地存储)：

```bash
# 会话持久化存储
DATABASE_URL=postgresql://user:pass@localhost:5432/workplan

# 云端图像存储
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=workplan-images
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
```

---

## 下一步

1. **启动 API**: 运行 `uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000`。
2. **使用 Swagger 测试**: 访问 http://localhost:8000/docs。
3. **与您的前端集成**: 使用上方提供的 JavaScript 示例代码。
4. **部署上线**: 使用 Gunicorn 或 Docker 进行生产环境部署。

---

## 技术支持

- **API 文档**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health
- **日志排查**: 查看控制台输出以获取调试信息。
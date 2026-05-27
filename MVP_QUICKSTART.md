# MVP 快速开始 (无需 Docker)

只需 3 分钟即可启动并运行 REST API Web 服务，无需依赖任何外部服务！

这是一个提供 REST API 接口用于生成工作计划的 **Web 服务**。

---

## 前置要求

- Python 3.11 及以上版本
- 豆包 (DouBao) API 密钥 (API key) 和推理接入点 (Endpoint)

## 第一步：环境配置 (30 秒)

```bash
cd workplan-generator
cp .env.example .env
```

编辑 `.env` 文件并**仅添加以下必填配置**：

```bash
DOUBAO_API_KEY=your_doubao_api_key_here
DOUBAO_BASE_URL=[https://ark.cn-beijing.volces.com/api/v3](https://ark.cn-beijing.volces.com/api/v3)
DOUBAO_MODEL=ep-your-endpoint-id
```

**配置完成！** 所有其他设置均为可选项。系统将默认使用：
- ✅ 内存检查点 (无需 PostgreSQL)
- ✅ 本地文件存储 (无需 S3/MinIO)
- ✅ 无需 Redis 或 Pinecone

## 第二步：安装依赖 (1 分钟)

```bash
python3 -m venv venv
source venv/bin/activate  # Windows 环境：venv\Scripts\activate
pip install -r requirements.txt
```

## 第三步：启动 Web 服务

```bash
# 启动 REST API 服务器
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**API 服务器运行地址**：http://localhost:8000

**交互式 API 文档**：http://localhost:8000/docs

## 第四步：测试 API

您可以使用以下任一方法测试该 Web 服务：

**浏览器 (交互式 Swagger UI)**:
```text
http://localhost:8000/docs
```

**Python 客户端示例** (模拟前端集成):
```bash
python test_client.py path/to/image.png "计算细胞数量"
```

**cURL**:
```bash
curl -X POST http://localhost:8000/sessions \
  -F "image=@image.png" \
  -F "description=计算阳性细胞的数量"
```

**JavaScript / 前端**:
```javascript
const formData = new FormData();
formData.append('image', imageFile);
formData.append('description', '计算细胞数量');

const response = await fetch('http://localhost:8000/sessions', {
  method: 'POST',
  body: formData
});
```

## 您将获得的功能 (MVP 阶段)

**REST API Web 服务**
- 包含会话 (Session) 管理的完整 REST API
- 交互式 API 文档 (Swagger UI)
- 启用跨域资源共享 (CORS)，方便前端集成

**三大智能体协同工作**
- 智能体 1：需求澄清者 (负责提问)
- 智能体 2：计划生成者 (负责创建工作计划)
- 智能体 3：计划审查者 (负责验证工作计划)

**基于 API 接口的完整工作流**
- 图像上传及视觉分析
- 循环澄清问答
- 工作计划生成
- 自动化审查循环
- 用户接受/拒绝机制

**会话持久化**
- 内存存储 (重启后会话将丢失，但这完全满足测试需求！)

## 重要注意事项

### 视觉 (Vision) 模型支持

**请检查您的豆包接入点是否支持视觉/多模态输入！**

智能体 1 需要分析显微镜图像。如果您的接入点不支持视觉处理：
- 系统依然可以运行
- 但智能体 1 将无法“看到”图像 (只能依靠您提供的文本描述)

测试视觉支持的示例代码：
```python
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(
    model="ep-your-endpoint-id",
    openai_api_key="your-api-key",
    openai_api_base="[https://ark.cn-beijing.volces.com/api/v3](https://ark.cn-beijing.volces.com/api/v3)",
)

# 尝试发送图像
message = HumanMessage(content=[
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    {"type": "text", "text": "这张图片里有什么？"}
])

response = llm.invoke([message])
print(response.content)
```

## 后续升级建议 (可选)

希望获得持久化存储和生产级特性？请将以下内容添加到 `.env` 文件中：

```bash
# 用于会话持久化的 PostgreSQL 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/workplan

# 用于图像存储的 S3/MinIO
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=workplan-images
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
```

然后启动 Docker 服务：
```bash
docker-compose up -d
```

## 故障排除

### "Module not found" (找不到模块)
```bash
pip install -r requirements.txt
```

### "DOUBAO_API_KEY not found" (找不到 API 密钥)
检查您的 `.env` 文件是否存在并配置了正确的值。

### "Connection refused" (连接被拒绝)
确保服务器正在运行：
```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 视觉功能无法工作
您的豆包接入点可能不支持图像。此时智能体 1 将降级至纯文本模式工作。

## 下一步

1. **与前端应用集成** - 参考 [BACKEND_API_GUIDE.md](BACKEND_API_GUIDE.md) 中的 JavaScript 示例。
2. **使用真实的显微镜图像进行测试** - 通过 API 接口进行上传。
3. **审查生成的工作计划** - 验证 API 的响应结果。
4. **自定义智能体提示词 (Prompts)** - 根据您的具体用例修改 `src/agents/` 目录中的提示词。
5. **添加系统提示词** - (将 `workplan_generator_system_prompt_v10_2.txt` 复制到项目根目录)。
6. **部署至生产环境** - 使用 Gunicorn 或 Docker (请参阅 [BACKEND_API_GUIDE.md](BACKEND_API_GUIDE.md))。

---

**就是这么简单！您现在已经拥有一个可以正常工作、用于生成工作计划的 REST API Web 服务了。**

开始与您的前端进行集成吧！ 
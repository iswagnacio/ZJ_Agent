# 工作计划生成器 - REST API Web 服务

这是一个使用 LangGraph 和豆包 (DouBao) 大语言模型构建的多智能体系统，旨在为成像分析生成专业的工作计划 (Workplan)。

**这是一个专为前端应用集成而设计的 REST API Web 服务。它的所有核心功能均通过 HTTP 接口向外提供。**

## 快速开始

```bash
cd workplan-generator

# 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 启动 API 服务器
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

**API 运行地址**：http://localhost:8000

**API 交互式文档**：http://localhost:8000/docs

**完整文档请参阅 [BACKEND_API_GUIDE.md](BACKEND_API_GUIDE.md)**

## 核心功能

接收显微镜图像 + 需求描述 → 生成经过验证的结构化工作计划 (JSON 格式)

**系统包含三个智能体 (Agents)：**
1. **需求澄清智能体 (Clarifier)**：通过提问深入理解您的分析需求。
2. **计划生成智能体 (Generator)**：创建结构化的工作计划 JSON。
3. **审查智能体 (Reviewer)**：验证工作计划的正确性和可行性。

## 系统架构

```text
用户上传图像 + 需求描述
    ↓
智能体 1 (澄清者) - 循环问答以明确需求
    ↓
智能体 2 (生成者) - 创建工作计划
    ↓
智能体 3 (审查者) - 验证计划 (必要时与智能体 2 循环交互修正)
    ↓
用户审查 - 接受计划 / 重新开始
    ↓
输出最终的工作计划 JSON
```

## 技术栈

- **LangGraph**：多智能体编排与状态管理
- **豆包 (DouBao)**：字节跳动大语言模型 (LLM)
- **FastAPI**：构建高性能 REST API
- **内存存储 (In-memory storage)**：MVP 阶段无需配置外部数据库

## Web 服务使用说明

本系统**完全作为一个 Web 服务运行**，所有功能均需通过 REST API 接口以 HTTP 请求的方式进行访问。

### 启动 API 服务器

```bash
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```

### 前端集成示例

```javascript
// 上传图像并初始化会话
const formData = new FormData();
formData.append('image', imageFile);
formData.append('description', '计算 Ki67 阳性细胞的数量');

const response = await fetch('http://localhost:8000/sessions', {
  method: 'POST',
  body: formData
});

const { session_id, questions } = await response.json();
```

### 客户端集成示例

任何标准 HTTP 客户端均可访问此 API：

```bash
# 交互式 API 文档 (Swagger UI)
open http://localhost:8000/docs

# Python 客户端示例 (演示集成方式)
python test_client.py microscope.png "计算细胞数量"

# cURL (命令行测试)
curl -X POST http://localhost:8000/sessions \
  -F "image=@microscope.png" \
  -F "description=计算阳性细胞的数量"
```

**注意**：`test_client.py` 仅为一个集成示例代码，用于演示如何通过 Python 调用 API。您的前端应用应构造并发送类似的 HTTP 请求。

## API 接口参考

| 接口路径 (Endpoint) | 请求方法 | 功能描述 |
|----------|--------|-------------|
| `/sessions` | POST | 上传图像和描述，初始化新会话 |
| `/sessions/{id}/respond` | POST | 回答智能体 1 (澄清者) 提出的问题 |
| `/sessions/{id}/decision` | POST | 接受当前工作计划或选择重新生成 |
| `/sessions/{id}` | GET | 获取当前会话的状态 |
| `/sessions/{id}/workplan` | GET | 下载最终生成的工作计划 JSON |
| `/health` | GET | 服务健康检查 |

**完整 API 文档请查阅**：[BACKEND_API_GUIDE.md](BACKEND_API_GUIDE.md)

## 环境配置

运行前需要在根目录下创建 `.env` 文件，最简配置要求如下：
```bash
DOUBAO_API_KEY=your_key
DOUBAO_BASE_URL=[https://ark.cn-beijing.volces.com/api/v3] (https://ark.cn-beijing.volces.com/api/v3)
DOUBAO_MODEL=ep-your-endpoint-id
```

就是这么简单！在 MVP（最小可行性产品）阶段，您无需配置任何数据库、S3 存储桶或 Docker 环境。

## 文档导航

- **[MVP_QUICKSTART.md](MVP_QUICKSTART.md)** - 新手请从这里开始！
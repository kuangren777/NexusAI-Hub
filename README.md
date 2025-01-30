# NexusAI Hub - AI模型聚合管理平台

## 项目简介
NexusAI Hub 是一个强大的 AI 模型聚合管理平台，支持多个 AI 服务提供商的统一接入和管理。该平台提供了一个用户友好的 Web 界面，支持实时对话测试、Token 计算、使用统计等功能，旨在简化 AI 服务的管理与交互，提升用户体验和效率。

## 主要特性
- 🚀 **多提供商支持**：可以统一管理多个 AI 服务提供商，方便不同平台的接入与管理。
- 🤖 **模型管理**：灵活配置和管理不同提供商的 AI 模型，支持模型的增、删、改、查操作。
- 💬 **实时对话**：通过 WebSocket 实现的实时对话测试，支持即时响应与交互。
- 📊 **数据统计**：详细展示对话轮次和 Token 使用统计，帮助用户了解使用情况。
- 🌓 **主题切换**：支持明暗两种主题模式，用户可以根据个人喜好调整界面风格。
- 🔐 **密钥管理**：提供安全的服务器密钥管理及个性化密钥管理机制，保障数据安全。
- 📝 **Token 计算**：支持多种模型的 Token 计算功能，实时估算 Token 使用量。

## 技术栈
- **后端**：FastAPI + SQLite + WebSocket
- **前端**：原生 JavaScript + HTML5 + CSS3
- **数据库**：SQLite3
- **工具库**：
  - **marked.js**：用于 Markdown 渲染。
  - **highlight.js**：用于代码高亮显示。
  - **Font Awesome**：提供图标支持。

## 系统架构
### 后端组件
1. **main.py**
   - FastAPI 应用的主入口文件。
   - 负责 API 路由处理。
   - 处理 WebSocket 实时通信。
   - 转发请求并处理响应。
   
2. **database.py**
   - 数据库初始化和管理文件。
   - 提供商和模型的 CRUD 操作。
   - 支持数据查询和统计功能。

3. **stats_tracker.py**
   - 跟踪对话统计信息。
   - 提供 Token 计算和估算功能。
   - 进行使用数据分析，帮助优化资源使用。

### 前端组件
1. **index.html**
   - 响应式用户界面设计，兼容不同设备。
   - 实时对话测试窗口。
   - 数据管理界面，方便查看和修改设置。
   - 统计展示面板，直观呈现使用数据。

## 数据库结构
### `service_providers` 表结构
```sql
CREATE TABLE service_providers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  server_url TEXT NOT NULL,
  server_key TEXT NOT NULL,
  personalized_key TEXT NOT NULL,
  description TEXT
);
```

### `provider_models` 表结构
```sql
CREATE TABLE provider_models (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  provider_id INTEGER NOT NULL,
  model_name TEXT NOT NULL,
  description TEXT,
  FOREIGN KEY (provider_id) REFERENCES service_providers (id),
  UNIQUE(provider_id, model_name)
);
```

### `chat_stats` 表结构
```sql
CREATE TABLE chat_stats (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp TEXT NOT NULL,
  conversation_id TEXT NOT NULL,
  provider_id INTEGER NOT NULL,
  model_name TEXT NOT NULL,
  tokens_count INTEGER NOT NULL,
  is_prompt BOOLEAN NOT NULL
);
```

## 安装和启动
1. 安装所需的 Python 包：
   ```bash
   pip install fastapi uvicorn aiosqlite httpx
   ```

2. 启动 FastAPI 应用：
   ```bash
   uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

## API接口文档

### OpenAI 兼容接口

NexusAI Hub 提供了与 OpenAI API 格式兼容的接口，可以直接替换 OpenAI 的接口地址使用。

#### 基础信息
- 接口地址：`http://your-domain:8001`
- 认证方式：Bearer Token（使用提供商的个性化密钥）
- 请求格式：JSON
- 响应格式：Stream 或 JSON

#### Chat Completions API

##### 1. 标准格式（OpenAI 兼容）
```http
POST /v1/chat/completions
Authorization: Bearer YOUR_PERSONALIZED_KEY
Content-Type: application/json

{
    "model": "MODEL_NAME",
    "messages": [
        {"role": "system", "content": "你是一个助手"},
        {"role": "user", "content": "你好"}
    ],
    "temperature": 0.7,
    "stream": true
}
```

##### 2. 简化格式
```http
POST /chat/completions
Authorization: Bearer YOUR_PERSONALIZED_KEY
Content-Type: application/json

{
    "model": "MODEL_NAME",
    "messages": [
        {"role": "user", "content": "你好"}
    ]
}
```

#### 响应格式

##### 流式响应 (stream=true)
```json
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694839621,"model":"gpt-3.5-turbo-0613","choices":[{"index":0,"delta":{"content":"你"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694839621,"model":"gpt-3.5-turbo-0613","choices":[{"index":0,"delta":{"content":"好"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694839621,"model":"gpt-3.5-turbo-0613","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1694839621,"model":"gpt-3.5-turbo-0613","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}
```

##### 非流式响应 (stream=false)
```json
{
    "id": "chatcmpl-123",
    "object": "chat.completion",
    "created": 1694839621,
    "model": "gpt-3.5-turbo-0613",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "你好！"
            },
            "finish_reason": "stop"
        }
    ],
    "usage": {
        "prompt_tokens": 10,
        "completion_tokens": 3,
        "total_tokens": 13
    }
}
```

#### 请求参数说明

| 参数名 | 类型 | 必选 | 说明 |
|--------|------|------|------|
| model | string | 是 | 模型名称，需要在管理后台配置 |
| messages | array | 是 | 对话消息数组 |
| temperature | float | 否 | 温度参数，控制随机性，默认 0.7 |
| stream | boolean | 否 | 是否使用流式响应，默认 true |

#### 错误响应
```json
{
    "error": {
        "message": "错误信息",
        "type": "invalid_request_error",
        "code": "invalid_api_key"
    }
}
```

### 使用示例

#### Python
```python
import openai

openai.api_key = "YOUR_PERSONALIZED_KEY"
openai.api_base = "http://your-domain:8001/v1"

response = openai.ChatCompletion.create(
    model="MODEL_NAME",
    messages=[
        {"role": "user", "content": "你好"}
    ],
    stream=True
)

for chunk in response:
    if chunk and chunk.choices and chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

#### JavaScript
```javascript
const response = await fetch('http://your-domain:8001/v1/chat/completions', {
    method: 'POST',
    headers: {
        'Authorization': `Bearer ${YOUR_PERSONALIZED_KEY}`,
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        model: 'MODEL_NAME',
        messages: [
            { role: 'user', content: '你好' }
        ],
        stream: true
    })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    
    const chunk = decoder.decode(value);
    const lines = chunk.split('\n');
    
    for (const line of lines) {
        if (line.startsWith('data: ')) {
            const data = JSON.parse(line.slice(6));
            if (data.choices[0].delta.content) {
                process.stdout.write(data.choices[0].delta.content);
            }
        }
    }
}
```

## 特色功能

1. **智能Token计算**
   - 支持中英文混合 Token 计算。
   - 提供快速估算功能，帮助用户实时了解 Token 使用情况。

2. **实时对话测试**
   - WebSocket 实时响应，支持流式输出。
   - 支持 Markdown 渲染，方便显示格式化文本。

3. **数据可视化**
   - 提供统计图表，直观展示对话和 Token 使用情况。
   - 实时更新数据，确保数据的准确性和时效性。

## 安全特性
- **服务器密钥加密存储**：所有服务器密钥使用加密技术安全存储。
- **个性化密钥访问控制**：通过权限管理系统，确保每个密钥的使用权限合理。
- **请求验证和鉴权**：采用标准的验证机制确保所有请求的合法性和安全性。

## 使用建议
1. **定期备份数据库**：为了防止数据丢失，建议定期进行数据库备份。
2. **及时更新服务器密钥**：定期更新密钥以提升安全性。
3. **监控 Token 使用情况**：定期检查 Token 使用情况，避免超出配额。
4. **根据需求调整模型配置**：根据不同的应用场景，灵活调整模型配置以提高效率和降低成本。

## 贡献指南
欢迎提交 Issues 和 Pull Requests，提交时请确保：
1. 代码符合项目规范，易于维护和扩展。
2. 提供完整的测试用例，确保功能的稳定性。
3. 更新相关文档，帮助其他开发者理解和使用项目。

## 许可证
MIT License

## 联系方式
- 项目维护者：kuangren
- 邮箱：luomingyu2002@126.com
- 项目地址：[\[GitHub Repository URL\]](https://github.com/kuangren777/NexusAI-Hub)

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

### 提供商管理
- `GET /providers`：获取所有提供商列表。
- `POST /providers`：添加新提供商。
- `PUT /providers/{provider_id}`：更新提供商信息。
- `DELETE /providers/{provider_id}`：删除指定的提供商。

### 模型管理
- `GET /providers/{provider_id}/models`：获取指定提供商的模型列表。
- `POST /provider_models`：添加新模型。
- `PUT /provider_models/{model_id}`：更新指定模型信息。
- `DELETE /provider_models/{model_id}`：删除指定模型。

### 对话接口
- `WebSocket /ws/chat`：实时对话接口，支持 WebSocket 协议进行聊天。
- `POST /v1/chat/completions`：标准对话接口，处理用户请求并返回模型的回答。
- `POST /chat/completions`：兼容接口，支持旧版接口的兼容。

### 统计接口
- `GET /stats/conversation/{conversation_id}`：获取特定对话的统计信息。
- `GET /stats/total`：获取总体的使用统计数据。

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
- 项目地址：[GitHub Repository URL]

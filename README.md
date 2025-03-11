# NexusAI API聚合平台

## 📌 项目概述
NexusAI API聚合平台 是一个轻量级的大语言模型 API 代理服务，专为简化多厂商 LLM API 管理而设计。本服务支持多个 LLM 服务提供商的统一管理，使用统一的接口规范与认证方式，并提供详细的 Token 使用统计。

## 🌟 核心功能

- **多提供商管理**：统一管理多个 LLM 服务提供商（如 OpenAI、Anthropic 等）及其 API 密钥
- **模型聚合**：支持每个提供商的多个模型管理
- **API 代理转发**：遵循 OpenAI API 格式，转发请求到指定的提供商模型
- **WebSocket 支持**：提供 WebSocket 接口，支持实时交互
- **Token 统计**：详细记录每次请求的 Token 使用情况
- **消息存储**：可选择保存请求与响应消息
- **流式输出支持**：支持 API 的流式响应模式

## 🛠️ 系统架构

本系统包含两个主要应用实例：
- **管理后台** (app_admin)：运行在 8000 端口，用于提供商和模型管理
- **API 服务** (app_api)：运行在 5231 端口，用于处理 LLM 请求代理

### 数据模型

```
服务提供商 (service_providers)
- id: 提供商唯一标识
- name: 提供商名称
- server_url: API 服务器地址
- server_key: API 密钥
- personalized_key: 个性化密钥（用于认证）
- description: 描述信息

提供商模型 (provider_models)
- id: 模型唯一标识
- provider_id: 关联的提供商 ID
- model_name: 模型名称
- description: 模型描述
```

## 🚀 快速开始

### 环境准备

```bash
# 安装依赖
pip install -r requirements.txt
```

### 启动服务

```bash
# 启动服务
python run.py
```

服务将同时启动：
- 管理后台：http://localhost:8000
- API 服务：http://localhost:5231

## 📡 API 参考

### 1. 管理 API

#### 提供商管理
- `GET /providers` - 获取所有提供商列表
- `POST /providers` - 创建新的提供商
- `GET /providers/{provider_id}` - 获取特定提供商信息
- `PUT /providers/{provider_id}` - 更新提供商信息
- `DELETE /providers/{provider_id}` - 删除提供商

#### 模型管理
- `POST /provider_models` - 创建新的模型
- `GET /providers/{provider_id}/models` - 获取特定提供商的所有模型
- `GET /provider_models/{model_id}` - 获取特定模型信息
- `PUT /provider_models/{model_id}` - 更新模型信息
- `DELETE /provider_models/{model_id}` - 删除模型

#### 统计信息
- `GET /stats/conversation/{conversation_id}` - 获取特定会话的统计信息
- `GET /stats/total` - 获取总体统计信息

### 2. LLM API

#### 聊天接口
- `POST /v1/chat/completions` - 标准聊天完成接口
- `POST /chat/completions` - 聊天完成接口的别名
- `WebSocket /ws/chat` - WebSocket 聊天接口

#### 模型接口
- `GET /v1/models` - 获取所有可用模型列表（符合OpenAI API格式）
- `GET /models` - 获取所有可用模型列表的别名接口

## 🧩 使用示例

### 1. 添加新的服务提供商

```bash
curl -X POST "http://localhost:8000/providers" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "OpenAI",
    "server_url": "https://api.openai.com/v1",
    "server_key": "your-openai-api-key",
    "personalized_key": "your-custom-key",
    "description": "OpenAI API 服务"
  }'
```

### 2. 添加模型

```bash
curl -X POST "http://localhost:8000/provider_models" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_id": 1,
    "model_name": "gpt-4",
    "description": "OpenAI GPT-4 模型"
  }'
```

### 3. 调用 LLM API

```bash
curl -X POST "http://localhost:5231/v1/chat/completions" \
  -H "Authorization: Bearer your-custom-key" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4",
    "messages": [{"role": "user", "content": "你好"}],
    "temperature": 0.7,
    "max_tokens": 500
  }'
```

### 4. 获取可用模型列表

```bash
curl -X GET "http://localhost:5231/v1/models" \
  -H "Authorization: Bearer your-custom-key"
```

响应示例：
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-4",
      "object": "model",
      "created": 1677610602,
      "owned_by": "OpenAI",
      "permission": [
        {
          "id": "modelperm-1",
          "object": "model_permission",
          "created": 1677610602,
          "allow_create_engine": false,
          "allow_sampling": true,
          "allow_logprobs": true,
          "allow_search_indices": false,
          "allow_view": true,
          "allow_fine_tuning": false,
          "organization": "*",
          "group": null,
          "is_blocking": false
        }
      ],
      "root": "gpt-4",
      "parent": null
    }
  ]
}
```

## 📊 统计功能

系统内置了详细的统计功能，记录：
- 每次对话的 Token 使用量
- 按提供商和模型的分类统计
- 支持查询特定会话的统计数据

## 🔍 调试功能

服务内置详细的日志功能，日志存储在 `logs` 目录中。

## 📝 注意事项

- 本服务需要有效的 LLM 服务提供商的 API 密钥
- 对于 Grok 模型，系统支持通过代理访问
- 数据库文件存储在 `data` 目录下
- 聊天记录（如果启用）存储在 `messages` 目录中

## 📄 许可证

[MIT License](LICENSE)
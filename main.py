from fastapi import FastAPI, HTTPException, WebSocket, Request, Response
from pydantic import BaseModel
from pathlib import Path
import httpx
import json
import asyncio
from database import (
    init_db, add_service_provider, get_all_providers,
    get_provider_info, delete_provider, update_provider,
    get_provider_by_id, add_provider_model, get_models_by_provider,
    get_model_by_id, DATABASE_PATH, update_provider_model, delete_provider_model,
    get_all_models
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
import sqlite3
import aiosqlite
from stats_tracker import StatsTracker
import uuid
import logging
from datetime import datetime, timedelta
import re
import traceback
from my_tokenizer import Tokenizer
from save_messages import save_message_to_file
from warnings import filterwarnings
import time
import random  # 添加随机模块导入
from httpx import AsyncClient, AsyncHTTPTransport  # 修改为异步传输类
import os
import secrets
from typing import List, Dict, Any, Optional
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

filterwarnings("ignore", category=DeprecationWarning)

# 创建多个应用实例
app_admin = FastAPI()  # 管理后台，例如端口8000
app_api = FastAPI()    # API接口，例如端口8001
app = FastAPI()

# 确保数据目录存在
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 初始化数据库
init_db()

# 初始化 StatsTracker
stats_tracker = StatsTracker()

# 初始化 Tokenizer
tokenizer = Tokenizer()

# 挂载静态文件目录到管理后台
app_admin.mount("/static", StaticFiles(directory="static"), name="static")

# 添加根路由返回 index.html
@app_admin.get("/")
async def read_index():
    return FileResponse("static/index.html")

# 数据模型
class ServiceProvider(BaseModel):
    name: str
    server_url: str
    server_key: str
    personalized_key: str
    description: str = ""

class ProviderModel(BaseModel):
    model_config = {"protected_namespaces": ()}
    
    provider_id: int
    model_name: str
    description: str = ""

class ProviderUpdate(BaseModel):
    name: str
    server_url: str
    server_key: str
    personalized_key: str
    description: str = ""

# 创建日志目录
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

# 配置日志
def setup_logger(name, log_file, level=logging.INFO):
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    
    # 文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # 创建logger
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

# 创建日志文件名（按日期）
log_file = LOG_DIR / f"debug_{datetime.now().strftime('%Y%m%d')}.log"
logger = setup_logger('nexusai', log_file)

# 调试模式配置
DEBUG_MODE = True  # 可以通过环境变量或配置文件设置

# 修改代理配置为URL字符串格式
PROXIES = [
    'http://192.168.88.205:8888',
    'http://192.168.88.249:7890'
]

# API 路由
@app_admin.post("/providers")
async def create_provider(provider: ServiceProvider):
    try:
        print(f"尝试添加新提供商: {provider}")
        add_service_provider(
            provider.name, 
            provider.server_url, 
            provider.server_key,
            provider.personalized_key,
            provider.description
        )
        return {"status": "success", "message": "服务提供商添加成功"}
    except sqlite3.IntegrityError as e:
        print(f"数据库完整性错误: {str(e)}")
        raise HTTPException(
            status_code=400, 
            detail=str(e)
        )
    except Exception as e:
        print(f"添加提供商时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app_admin.post("/provider_models")
async def create_provider_model(model: ProviderModel):
    try:
        add_provider_model(
            model.provider_id,
            model.model_name,
            model.description
        )
        return {"status": "success", "message": "模型添加成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app_admin.get("/providers/{provider_id}/models")
async def get_provider_models(provider_id: int):
    try:
        models = get_models_by_provider(provider_id)
        if not models:
            models = []
        # 不要重新编号，保留原始ID
        return {"models": models}
    except Exception as e:
        print(f"获取提供商模型时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app_admin.get("/providers")
async def list_providers():
    try:
        providers = get_all_providers()
        # 按ID排序并重新编号
        sorted_providers = sorted(providers, key=lambda x: x[0])
        renumbered_providers = []
        for i, provider in enumerate(sorted_providers, 1):
            # 创建新的元组，将第一个元素（ID）替换为新的序号，并移除敏感信息
            renumbered_provider = (
                i,                    # 新的序号
                provider[1],          # name
                provider[2],          # server_url
                provider[3],          # server_key
                provider[4],          # personalized_key
                provider[5]           # description
            )
            renumbered_providers.append(renumbered_provider)
        return {"providers": renumbered_providers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# WebSocket 聊天接口
@app_admin.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    async def send_message(message: str, provider_id: int, model_name: str):
        try:
            conversation_id = str(uuid.uuid4())
            
            # 计算并记录发送的prompt tokens
            prompt_tokens = await tokenizer.count_tokens(message)
            
            logger.info(f"""
WebSocket Token使用统计 [会话ID: {conversation_id}]
------------------------
发送统计:
- 模型: {model_name}
- Prompt Tokens: {prompt_tokens}
- 提供商ID: {provider_id}
------------------------
""")
            
            provider_info = get_provider_info(provider_id)
            if not provider_info:
                await websocket.send_text(json.dumps({
                    "error": "无效的提供商ID"
                }))
                return

            if model_name not in provider_info["models"]:
                await websocket.send_text(json.dumps({
                    "error": "该提供商未配置此模型"
                }))
                return

            server_url = provider_info["server_url"]
            server_key = provider_info["server_key"]
            
            # 生成会话ID
            conversation_id = str(uuid.uuid4())
            
            # 计算并记录发送的prompt tokens
            prompt_tokens = await tokenizer.count_tokens(message)
            await stats_tracker.record_chat(
                conversation_id=conversation_id,
                provider_id=provider_id,
                model_name=model_name,
                tokens_count=prompt_tokens,
                is_prompt=True
            )
            
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {server_key}",
                    "Content-Type": "application/json"
                }
                
                payload = {
                    "model": model_name,
                    "messages": [
                        {"role": "user", "content": message}
                    ],
                    "temperature": 0.7,
                    "stream": True
                }
                
                print(f"发送请求: {payload}")  # 调试日志
                async with client.stream('POST', 
                    f"{server_url.rstrip('/')}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                    timeout=30.0
                ) as response:
                    if response.status_code != 200:
                        error_text = f"服务器错误: {response.status_code}"
                        print(f"错误: {error_text}")  # 调试日志
                        await websocket.send_text(json.dumps({
                            "error": error_text
                        }))
                        return
                    
                    current_content = ""
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data.get("choices") and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        current_content += delta["content"]
                                        await websocket.send_text(json.dumps({
                                            "content": current_content,
                                            "type": "message"
                                        }))
                            except json.JSONDecodeError:
                                continue
                    
                    # 计算并记录接收到的completion tokens
                    if current_content:
                        completion_tokens = await tokenizer.count_tokens(current_content)
                        await stats_tracker.record_chat(
                            conversation_id=conversation_id,
                            provider_id=provider_id,
                            model_name=model_name,
                            tokens_count=completion_tokens,
                            is_prompt=False,
                            message=current_content  # 记录完整的响应消息
                        )
                
            # 在接收完整响应后
            if current_content:
                completion_tokens = await tokenizer.count_tokens(current_content)
                
                logger.info(f"""
WebSocket Token使用统计 [会话ID: {conversation_id}]
------------------------
接收统计:
- 模型: {model_name}
- Completion Tokens: {completion_tokens}
- 总计 Tokens: {prompt_tokens + completion_tokens}
- 提供商ID: {provider_id}
------------------------
""")
                
                await stats_tracker.record_chat(
                    conversation_id=conversation_id,
                    provider_id=provider_id,
                    model_name=model_name,
                    tokens_count=completion_tokens,
                    is_prompt=False,
                    message=current_content
                )
                
        except Exception as e:
            logger.error(f"""
WebSocket错误 [会话ID: {conversation_id if 'conversation_id' in locals() else 'N/A'}]
------------------------
- 模型: {model_name}
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- 提供商ID: {provider_id}
------------------------
""")
            await websocket.send_text(json.dumps({
                "error": f"错误: {str(e)}"
            }))

    try:
        while True:
            data = await websocket.receive_text()
            print(f"收到WebSocket消息: {data}")  # 调试日志
            message_data = json.loads(data)
            await send_message(
                message_data["message"],
                int(message_data["provider_id"]),
                message_data["model_name"]
            )
    except Exception as e:
        print(f"WebSocket错误: {str(e)}")
        await websocket.close()

# 添加删除路由
@app_admin.delete("/providers/{provider_id}")
async def delete_service_provider(provider_id: int):
    try:
        delete_provider(provider_id)
        return {"status": "success", "message": "服务提供商删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加更新路由
@app_admin.put("/providers/{provider_id}")
async def update_service_provider(provider_id: int, provider: ProviderUpdate):
    try:
        existing_provider = get_provider_by_id(provider_id)
        if not existing_provider:
            raise HTTPException(status_code=404, detail="提供商不存在")
        
        result = update_provider(
            provider_id,
            provider.name,
            provider.server_url,
            provider.server_key,
            provider.personalized_key,
            provider.description
        )
        return {"status": "success", "message": "服务提供商更新成功"}
    except Exception as e:
        print(f"更新提供商错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# 添加获取单个记录的路由
@app_admin.get("/providers/{provider_id}")
async def get_provider(provider_id: int):
    try:
        provider = get_provider_by_id(provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        return {
            "id": provider[0],
            "name": provider[1],
            "server_url": provider[2],
            "server_key": provider[3],  # 显示真实密钥
            "personalized_key": provider[4],  # 显示真实密钥
            "description": provider[5]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加获取可用提供商的路由
@app_admin.get("/providers/available")
async def list_available_providers():
    """获取所有提供商列表"""
    try:
        providers = get_all_providers()
        return {"providers": providers}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加获取单个模型的路由
@app_admin.get("/provider_models/{model_id}")
async def get_model(model_id: int):
    try:
        model = get_model_by_id(model_id)
        if not model:
            raise HTTPException(status_code=404, detail="Model not found")
        # 返回原始数据结构，不做修改
        return {
            "id": model[0],
            "provider_id": model[1],
            "model_name": model[2],
            "description": model[3]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加更新模型的路由
@app_admin.put("/provider_models/{model_id}")
async def update_model(model_id: int, model: ProviderModel):
    try:
        update_provider_model(
            model_id,
            model.provider_id,
            model.model_name,
            model.description
        )
        return {"status": "success", "message": "模型更新成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加删除模型的路由
@app_admin.delete("/provider_models/{model_id}")
async def delete_model(model_id: int):
    try:
        delete_provider_model(model_id)
        return {"status": "success", "message": "模型删除成功"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 添加验证个性化密钥的函数
async def verify_personalized_key(personalized_key: str, model_name: str):
    """验证个性化密钥是否对应指定模型的提供商"""
    async with aiosqlite.connect(str(DATABASE_PATH)) as db:
        async with db.execute("""
            SELECT sp.id 
            FROM service_providers sp
            JOIN provider_models pm ON sp.id = pm.provider_id
            WHERE sp.personalized_key = ? AND pm.model_name = ?
        """, (personalized_key, model_name)) as cursor:
            result = await cursor.fetchone()
            return result[0] if result else None

# 添加一个新的统计路由
@app_admin.get("/stats/conversation/{conversation_id}")
async def get_conversation_stats(conversation_id: str):
    return await stats_tracker.get_conversation_stats(conversation_id)

@app_admin.get("/stats/total")
async def get_total_stats():
    return await stats_tracker.get_total_stats()

# 添加一个通用的流式处理函数
async def handle_chat_completions(request: Request):
    """统一处理聊天请求，根据baseurl选择最终路径"""
    try:
        body = await request.json()
        messages = body.get("messages", [])
        count_text = ""
        
        # 确保 messages 是字符串而不是列表
        if isinstance(messages, list):
            # 提取内容，确保每个元素都是字符串
            # messages = []
            for msg in messages:
                if isinstance(msg, dict):
                    # 如果是字典，提取内容
                    content = msg.get("content", "")
                    if isinstance(content, list):
                        for item in content:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    count_text += item.get("text", "")
                    elif isinstance(content, str):
                        count_text += content
                elif isinstance(msg, str):
                    count_text += msg
                # 处理文件数据（如图片）
                elif isinstance(msg, list):
                    # 这里可以根据需要处理文件数据
                    # 例如，记录文件信息或将其转换为字符串
                    count_text += "包含文件数据"  # 你可以自定义处理逻辑

        else:
            count_text = str(messages)  # 如果不是列表，转换为列表

        prompt_text = count_text  # 确保 prompt_text 是字符串
        
        # 尝试从最后一条用户消息中找到相关会话
        conversation_id = None
        if messages:
            last_message = messages[-1]
            last_conversation = await stats_tracker.get_last_conversation(last_message)
            if last_conversation:
                conversation_id = last_conversation["conversation_id"]
        
        # 如果没找到相关会话，创建新的会话ID
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        if DEBUG_MODE:
            logger.info(f"开始处理新的请求 [会话ID: {conversation_id}]")
        
        # 获取Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            if DEBUG_MODE:
                logger.error("缺少有效的Authorization header")
            raise HTTPException(status_code=401, detail="缺少有效的Authorization header")
        
        personalized_key = auth_header.split(" ")[1]
        
        # 读取请求体
        body = await request.json()
        is_stream = body.get("stream", False)
        
        if DEBUG_MODE:
            if DEBUG_MODE == "Detail":
                logger.info(f"请求体: {json.dumps(body, ensure_ascii=False, indent=2)}")
                logger.info(f"请求头: {dict(request.headers)}")
            logger.info(f"是否使用流式传输: {is_stream}")
        
        model_name = body.get("model")
        if not model_name:
            if DEBUG_MODE:
                logger.error("缺少model参数")
            raise HTTPException(status_code=400, detail="缺少model参数")
        
        # 检查是否为Grok模型
        is_grok_model = "grok" in model_name.lower()
        if DEBUG_MODE and is_grok_model:
            logger.info(f"检测到Grok模型: {model_name}")
        
        # 验证个性化密钥
        provider_id = await verify_personalized_key(personalized_key, model_name)
        if not provider_id:
            if DEBUG_MODE:
                logger.error(f"无效的API密钥或该密钥无权访问模型: {model_name}")
            raise HTTPException(status_code=401, detail="无效的API密钥或该密钥无权访问指定模型")
        
        # 获取提供商信息
        provider_info = get_provider_info(provider_id)
        if not provider_info:
            if DEBUG_MODE:
                logger.error("提供商配置不存在")
            raise HTTPException(status_code=404, detail="提供商配置不存在")
        
        if model_name not in provider_info["models"]:
            if DEBUG_MODE:
                logger.error(f"不支持的模型: {model_name}")
            raise HTTPException(status_code=400, detail="不支持的模型")
        
        # 计算并记录发送的prompt tokens
        prompt_tokens = await tokenizer.count_tokens(prompt_text)
        
        logger.info(f"""
Token使用统计 [会话ID: {conversation_id}]
------------------------
发送统计:
- 模型: {model_name}
- Prompt Tokens: {prompt_tokens}
- 提供商ID: {provider_id}
------------------------
""")
        
        await stats_tracker.record_chat(
            conversation_id=conversation_id,
            provider_id=provider_id,
            model_name=model_name,
            tokens_count=prompt_tokens,
            is_prompt=True
        )

        # 保存请求信息
        save_message_to_file({
            "timestamp": datetime.now().isoformat(),
            "headers": dict(request.headers),
            "target_url": str(request.url),
            "client_host": request.client.host if request.client else None,
            "request_body": body,
            "conversation_content": {
                "prompt": prompt_text,
                "completion": ""  # 稍后补充
            }
        })

        # 随机选择代理（仅限Grok模型）
        proxy = random.choice(PROXIES) if is_grok_model else None
        
        # 创建带代理的客户端（仅限Grok模型）
        client = AsyncClient(transport=AsyncHTTPTransport(proxy=proxy)) if is_grok_model else AsyncClient()
        
        # 简化URL构建逻辑
        base_url = provider_info['server_url'].rstrip('/')
        
        # 如果URL以'/'结尾，直接使用chat/completions
        if provider_info['server_url'].endswith(('/')):
            upstream_url = f"{base_url}/chat/completions"
        # 如果URL以'#'结尾，后面不加任何内容
        elif provider_info['server_url'].endswith(('#')):
            upstream_url = f"{base_url}"
        else:
            # 默认行为：添加 /v1/chat/completions
            upstream_url = f"{base_url}/v1/chat/completions"

        if DEBUG_MODE:
            logger.info(f"上游请求URL: {upstream_url}")
        headers = {
            "Authorization": f"Bearer {provider_info['server_key']}",
            "Content-Type": "application/json"
        }

        # 增加重试次数和延迟
        retry_count = 3
        retry_delay = 5

        if not is_stream:
            if DEBUG_MODE:
                logger.info("使用非流式响应")
            for attempt in range(retry_count):
                try:
                    # 创建带代理的异步transport（仅限Grok模型）
                    if is_grok_model:
                        proxy_url = random.choice(PROXIES)
                        transport = AsyncHTTPTransport(proxy=proxy_url)
                        client = AsyncClient(transport=transport)
                    else:
                        client = AsyncClient()

                    if attempt > 0 and DEBUG_MODE:
                        logger.info(f"第 {attempt + 1} 次重试请求")
                    
                    # 增加超时时间，特别是对于Grok模型
                    timeout = 300.0 if is_grok_model else 120.0
                    
                    if DEBUG_MODE:
                        logger.info(f"设置请求超时时间: {timeout}秒")
                    
                    response = await client.post(
                        upstream_url,
                        json=body,
                        headers=headers,
                        timeout=timeout
                    )
                    break  # 如果请求成功，跳出重试循环
                    
                except (httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                    if attempt == retry_count - 1:  # 最后一次尝试
                        raise HTTPException(
                            status_code=504,
                            detail={
                                "error": "请求超时",
                                "type": "timeout_error",
                                "message": f"上游服务器响应时间过长或连接超时 ({type(e).__name__})",
                                "attempts": retry_count
                            }
                        )
                    await asyncio.sleep(retry_delay)  # 等待一段时间后重试
                    
                except httpx.RequestError as e:
                    logger.error(f"请求错误 [尝试次数: {attempt + 1}/{retry_count}] - 错误信息: {str(e)}")
                    if attempt == retry_count - 1:  # 最后一次尝试
                        raise HTTPException(
                            status_code=502,
                            detail={
                                "error": str(e),
                                "type": "request_error",
                                "message": "与上游服务器通信时发生错误"
                            }
                        )
                    await asyncio.sleep(retry_delay)  # 等待一段时间后重试
                finally:
                    if attempt == retry_count - 1:  # 最后一次尝试后关闭客户端
                        await client.aclose()
            
            if response.status_code != 200:
                if DEBUG_MODE:
                    logger.error(f"上游服务器错误: {response.status_code}")
                # 获取响应头
                headers = dict(response.headers)
                # 解析响应内容
                try:
                    error_content = response.json()
                except:
                    error_content = response.text

                # 直接返回响应，保留状态码和响应头
                return Response(
                    content=json.dumps(error_content),
                    status_code=response.status_code,
                    headers={
                        # 转发关键的速率限制响应头
                        "X-RateLimit-Limit": headers.get("X-RateLimit-Limit", ""),
                        "X-RateLimit-Remaining": headers.get("X-RateLimit-Remaining", ""),
                        "X-RateLimit-Reset": headers.get("X-RateLimit-Reset", ""),
                        "Content-Type": "application/json"
                    }
                )
            
            if DEBUG_MODE:
                logger.info(f"非流式响应内容: {response.text}")
            
            # 在成功接收响应后
            completion_text = ""  # 初始化变量
            if response.status_code == 200:
                try:
                    response_data = response.json()
                    
                    # 记录原始响应数据，用于调试
                    if DEBUG_MODE == "Detail":
                        logger.info(f"原始响应数据结构: {json.dumps(response_data, ensure_ascii=False)}")
                    
                    # 处理Grok模型的特殊返回格式
                    if is_grok_model:
                        if DEBUG_MODE == "Detail":
                            logger.info("处理Grok模型的响应格式")
                        
                        # 转换Grok格式为OpenAI标准格式
                        if "choices" in response_data and len(response_data["choices"]) > 0:
                            choice = response_data["choices"][0]
                            
                            # 检查是否有message字段
                            if "message" in choice:
                                if isinstance(choice["message"], dict):
                                    # 标准格式：message是一个字典
                                    completion_text = choice["message"].get("content", "")
                                    
                                    # 确保message有正确的role字段
                                    if "role" not in choice["message"]:
                                        choice["message"]["role"] = "assistant"
                                elif isinstance(choice["message"], str):
                                    # 非标准格式：message是一个字符串
                                    completion_text = choice["message"]
                                    # 转换为标准格式
                                    choice["message"] = {
                                        "role": "assistant",
                                        "content": completion_text
                                    }
                            # 如果没有message字段但有text字段（某些API的变体）
                            elif "text" in choice:
                                completion_text = choice["text"]
                                # 添加标准格式的message字段
                                choice["message"] = {
                                    "role": "assistant",
                                    "content": completion_text
                                }
                            # 如果没有message字段但有content字段（另一种变体）
                            elif "content" in choice:
                                completion_text = choice["content"]
                                # 添加标准格式的message字段
                                choice["message"] = {
                                    "role": "assistant",
                                    "content": completion_text
                                }
                            
                            # 重新序列化为JSON
                            response_text = json.dumps(response_data)
                        else:
                            if DEBUG_MODE:
                                logger.warning("Grok响应中未找到有效的choices字段")
                            # 尝试从其他可能的字段中提取内容
                            if "response" in response_data:
                                completion_text = response_data["response"]
                                # 构造一个符合OpenAI格式的响应
                                new_response = {
                                    "id": response_data.get("id", f"grok-{uuid.uuid4()}"),
                                    "object": "chat.completion",
                                    "created": int(datetime.now().timestamp()),
                                    "model": model_name,
                                    "choices": [{
                                        "index": 0,
                                        "message": {
                                            "role": "assistant",
                                            "content": completion_text
                                        },
                                        "finish_reason": "stop"
                                    }]
                                }
                                response_text = json.dumps(new_response)
                    else:
                        # 标准OpenAI格式处理
                        if response_data.get("choices") and len(response_data["choices"]) > 0:
                            completion_text = response_data["choices"][0].get("message", {}).get("content", "")
                        response_text = response.text
                    
                    if not completion_text and DEBUG_MODE:
                        logger.warning(f"无法从响应中提取完成文本，原始响应: {response.text}")
                
                except json.JSONDecodeError as e:
                    if DEBUG_MODE:
                        logger.error(f"JSON解析错误: {str(e)}, 响应内容: {response.text}")
                    # 如果无法解析JSON，返回原始响应
                    response_text = response.text
                except Exception as e:
                    if DEBUG_MODE:
                        logger.error(f"处理响应时发生错误: {str(e)}")
                    # 发生其他错误时，返回原始响应
                    response_text = response.text
                
                if completion_text:
                    completion_tokens = await tokenizer.count_tokens(completion_text)
                    
                    logger.info(f"""
Token使用统计 [会话ID: {conversation_id}]
------------------------
接收统计:
- 模型: {model_name}
- Completion Tokens: {completion_tokens}
- 总计 Tokens: {prompt_tokens + completion_tokens}
- 提供商ID: {provider_id}
------------------------
""")
                    
                    await stats_tracker.record_chat(
                        conversation_id=conversation_id,
                        provider_id=provider_id,
                        model_name=model_name,
                        tokens_count=completion_tokens,
                        is_prompt=False,
                        message=completion_text
                    )

            # 更新保存的完成内容
            if completion_text:
                save_message_to_file({
                    "timestamp": datetime.now().isoformat(),
                    "conversation_content": {
                        "completion": completion_text
                    }
                })
            
            return Response(
                content=response_text if 'response_text' in locals() else response.text,
                media_type="application/json"
            )
        
        if DEBUG_MODE:
            logger.info("使用流式响应")
        
        async def stream_generator():
            current_content = ""
            try:
                # 创建带代理的异步transport（仅限Grok模型）
                if is_grok_model:
                    proxy_url = random.choice(PROXIES)
                    transport = AsyncHTTPTransport(proxy=proxy_url)
                    client = AsyncClient(transport=transport)
                else:
                    client = AsyncClient()

                # 增加超时时间，特别是对于Grok模型
                timeout = 300.0 if is_grok_model else 60.0
                
                if DEBUG_MODE == "Detail":
                    logger.info(f"设置流式请求超时时间: {timeout}秒")
                
                async with client.stream(
                    'POST',
                    upstream_url,
                    json={**body, "stream": True},
                    headers=headers,
                    timeout=timeout
                ) as response:
                    if response.status_code != 200:
                        error_response = await response.aread()
                        if DEBUG_MODE:
                            logger.error(f"上游服务器错误: {response.status_code}, 响应内容: {error_response}")
                        error_msg = {
                            "error": {
                                "message": f"上游服务器错误: {response.status_code}",
                                "type": "upstream_error",
                                "code": response.status_code,
                                "upstream_response": error_response.decode('utf-8', errors='ignore')
                            }
                        }
                        yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n".encode('utf-8')
                        return

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 过滤非数据行和心跳信号
                        if line.startswith(':'):  # 过滤以冒号开头的SSE注释行
                            if DEBUG_MODE == "Detail":
                                logger.info(f"跳过心跳/注释行: {line}")
                            continue
                        
                        # 处理特殊结束标记
                        if "[DONE]" in line:
                            if DEBUG_MODE == "Detail":
                                logger.info("接收到流式结束标记 [DONE]")
                            yield "data: [DONE]\n\n".encode('utf-8')
                            continue
                        
                        try:
                            # 改进数据提取逻辑
                            if line.startswith('data: '):
                                data_str = line[6:].strip()
                            else:
                                data_str = line  # 尝试解析整行作为数据
                            
                            if not data_str or data_str == "[DONE]":
                                continue
                            
                            if DEBUG_MODE == "Detail":
                                logger.info(f"尝试解析的数据内容: {data_str}")
                            
                            data = json.loads(data_str)
                            
                            # 处理Grok模型的流式响应
                            if is_grok_model:
                                if DEBUG_MODE == "Detail":
                                    logger.info(f"处理Grok流式响应: {json.dumps(data, ensure_ascii=False)}")
                                
                                # 确保数据有正确的结构
                                if "choices" not in data:
                                    data["choices"] = [{"index": 0}]
                                elif not data["choices"]:
                                    data["choices"] = [{"index": 0}]
                                
                                choice = data["choices"][0]
                                content = ""
                                
                                # 检查各种可能的字段格式
                                if "delta" in choice:
                                    # 已经是delta格式，检查内容
                                    if isinstance(choice["delta"], dict):
                                        if "content" in choice["delta"]:
                                            content = choice["delta"]["content"]
                                        # 确保有role字段
                                        if "role" not in choice["delta"]:
                                            choice["delta"]["role"] = "assistant"
                                    elif isinstance(choice["delta"], str):
                                        content = choice["delta"]
                                        choice["delta"] = {
                                            "role": "assistant",
                                            "content": content
                                        }
                                elif "message" in choice:
                                    # 需要转换message为delta
                                    if isinstance(choice["message"], dict):
                                        content = choice["message"].get("content", "")
                                        role = choice["message"].get("role", "assistant")
                                    else:
                                        content = str(choice["message"])
                                        role = "assistant"
                                    
                                    # 创建标准delta格式
                                    choice["delta"] = {
                                        "role": role,
                                        "content": content
                                    }
                                    # 删除原始message字段
                                    del choice["message"]
                                elif "text" in choice:
                                    content = choice["text"]
                                    choice["delta"] = {
                                        "role": "assistant",
                                        "content": content
                                    }
                                    del choice["text"]
                                elif "content" in choice:
                                    content = choice["content"]
                                    choice["delta"] = {
                                        "role": "assistant",
                                        "content": content
                                    }
                                    del choice["content"]
                                else:
                                    # 找不到任何内容字段，创建空delta
                                    choice["delta"] = {
                                        "role": "assistant",
                                        "content": ""
                                    }
                                
                                # 确保其他必要字段存在
                                if "index" not in choice:
                                    choice["index"] = 0
                                
                                # 确保基本字段存在
                                if "id" not in data:
                                    data["id"] = f"chatcmpl-{uuid.uuid4()}"
                                if "object" not in data:
                                    data["object"] = "chat.completion.chunk"
                                if "created" not in data:
                                    data["created"] = int(time.time())
                                if "model" not in data:
                                    data["model"] = model_name
                                
                                if content:
                                    current_content += content
                                
                                if DEBUG_MODE == "Detail":
                                    logger.info(f"转换后的Grok流式响应: {json.dumps(data, ensure_ascii=False)}")
                            
                            # 发送处理后的数据
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode('utf-8')
                            
                        except json.JSONDecodeError as e:
                            if DEBUG_MODE:
                                logger.warning(f"跳过无法解析的数据: {line} | 错误: {str(e)}")
                            continue  # 跳过无效数据继续处理
                        except Exception as e:
                            if DEBUG_MODE:
                                logger.error(f"处理数据时发生意外错误: {str(e)}")
                            continue
                    
                    # 确保发送结束标记
                    yield "data: [DONE]\n\n".encode('utf-8')
                    
                    # 在流式响应结束后保存完整内容
                    if current_content:
                        completion_tokens = await tokenizer.count_tokens(current_content)
                        
                        logger.info(f"""
Token使用统计 [会话ID: {conversation_id}]
------------------------
流式响应统计:
- 模型: {model_name}
- Prompt Tokens: {prompt_tokens}
- Completion Tokens: {completion_tokens}
- 总计 Tokens: {prompt_tokens + completion_tokens}
- 提供商ID: {provider_id}
------------------------
""")
                        save_message_to_file({
                            "timestamp": datetime.now().isoformat(),
                            "conversation_content": {
                                "completion": current_content
                            }
                        })

            except httpx.ConnectError as e:
                logger.error(f"""
连接错误 [会话ID: {conversation_id}]
------------------------
- 模型: {model_name}
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- 提供商ID: {provider_id}
------------------------
""")
                error_msg = {
                    "error": {
                        "message": f"连接错误: {str(e)}",
                        "type": "connection_error",
                        "code": 500
                    }
                }
                yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n".encode('utf-8')
                yield "data: [DONE]\n\n".encode('utf-8')
            except Exception as e:
                logger.error(f"""
错误统计 [会话ID: {conversation_id}]
------------------------
- 模型: {model_name}
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- 提供商ID: {provider_id}
------------------------
""")
                error_msg = {
                    "error": {
                        "message": f"处理流式响应时发生错误: {str(e)}",
                        "type": "stream_error",
                        "code": 500
                    }
                }
                yield f"data: {json.dumps(error_msg, ensure_ascii=False)}\n\n".encode('utf-8')
                yield "data: [DONE]\n\n".encode('utf-8')
            
            finally:
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
                "X-Accel-Buffering": "no",
                "Content-Type": "text/event-stream",
                "X-Conversation-Id": conversation_id
            }
        )

    except Exception as e:
        logger.error(f"""
系统错误 [会话ID: {conversation_id if 'conversation_id' in locals() else 'N/A'}]
------------------------
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- 堆栈跟踪:
{traceback.format_exc()}
------------------------
""")
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "type": "server_error",
                "message": "处理请求时发生内部错误"
            }
        )

# API接口路由
@app_api.post("/v1/chat/completions")
async def chat_completions_v1(request: Request):
    """标准 v1 接口"""
    return await handle_chat_completions(request)

@app_api.post("/chat/completions")
async def chat_completions(request: Request):
    """将非版本号请求重定向到 v1 接口"""
    return await handle_chat_completions(request)

@app_api.get("/v1/models")
async def list_models():
    """
    获取所有可用模型列表，返回格式符合OpenAI API规范
    """
    try:
        # 从数据库获取所有模型
        models_data = get_all_models()
        
        # 按照OpenAI格式构建响应
        formatted_models = []
        for model in models_data:
            model_id, provider_id, model_name, description, provider_name = model
            formatted_models.append({
                "id": model_name,
                "object": "model",
                "created": int(time.time()),
                "owned_by": provider_name,
                "permission": [
                    {
                        "id": f"modelperm-{model_id}",
                        "object": "model_permission",
                        "created": int(time.time()),
                        "allow_create_engine": False,
                        "allow_sampling": True,
                        "allow_logprobs": True,
                        "allow_search_indices": False,
                        "allow_view": True,
                        "allow_fine_tuning": False,
                        "organization": "*",
                        "group": None,
                        "is_blocking": False
                    }
                ],
                "root": model_name,
                "parent": None
            })
        
        return {
            "object": "list",
            "data": formatted_models
        }
    except Exception as e:
        logger.error(f"获取模型列表时出错: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取模型列表失败: {str(e)}")

# 添加一个别名路由，不带v1前缀
@app_api.get("/models")
async def list_models_alias():
    return await list_models()

# 添加测试路由
@app_admin.post("/test")
async def test_endpoint(request: Request):
    """
    测试接口，返回所有请求信息
    """
    # 获取所有请求头
    headers = dict(request.headers)
    
    # 获取请求体
    body = await request.body()
    try:
        # 尝试解析 JSON
        body_json = await request.json()
    except:
        body_json = None
    
    # 获取查询参数
    query_params = dict(request.query_params)
    
    # 获取客户端信息
    client = request.client.host if request.client else None
    
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": headers,
        "body_raw": body.decode() if body else None,
        "body_json": body_json,
        "query_params": query_params,
        "client_host": client,
        "cookies": dict(request.cookies),
        "path_params": request.path_params,
    }

# 也添加一个 GET 方法的测试路由
@app_admin.get("/test")
async def test_endpoint_get(request: Request):
    """
    GET 方法的测试接口
    """
    return {
        "method": request.method,
        "url": str(request.url),
        "headers": dict(request.headers),
        "query_params": dict(request.query_params),
        "client_host": request.client.host if request.client else None,
        "cookies": dict(request.cookies),
        "path_params": request.path_params,
    }

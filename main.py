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
    get_model_by_id, DATABASE_PATH, update_provider_model, delete_provider_model
)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
import sqlite3
import aiosqlite
from stats_tracker import StatsTracker
import uuid
import logging
from datetime import datetime
import re
import traceback
from my_tokenizer import Tokenizer

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
        
        # 尝试从最后一条用户消息中找到相关会话
        conversation_id = None
        if messages:
            last_message = messages[-1].get("content", "")
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
        prompt_text = "\n".join([msg.get("content", "") for msg in messages])
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

        client = httpx.AsyncClient()
        
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

        if not is_stream:
            if DEBUG_MODE:
                logger.info("使用非流式响应")
            retry_count = 3  # 最大重试次数
            retry_delay = 5  # 重试间隔（秒）
            
            for attempt in range(retry_count):
                try:
                    if attempt > 0 and DEBUG_MODE:
                        logger.info(f"第 {attempt + 1} 次重试请求")
                    
                    response = await client.post(
                        upstream_url,
                        json=body,
                        headers=headers,
                        timeout=2000.0  # 增加到5分钟
                    )
                    break  # 如果请求成功，跳出重试循环
                    
                except httpx.ReadTimeout:
                    if DEBUG_MODE:
                        logger.error(f"请求超时（第 {attempt + 1} 次尝试）：上游服务器响应时间过长")
                    if attempt == retry_count - 1:  # 最后一次尝试
                        raise HTTPException(
                            status_code=504,
                            detail={
                                "error": "请求超时",
                                "type": "timeout_error",
                                "message": "上游服务器响应时间过长，请稍后重试",
                                "attempts": retry_count
                            }
                        )
                    await asyncio.sleep(retry_delay)  # 等待一段时间后重试
                    
                except httpx.RequestError as e:
                    if DEBUG_MODE:
                        logger.error(f"请求错误: {str(e)}")
                    raise HTTPException(
                        status_code=502,
                        detail={
                            "error": str(e),
                            "type": "request_error",
                            "message": "与上游服务器通信时发生错误"
                        }
                    )
                finally:
                    if attempt == retry_count - 1:  # 最后一次尝试后关闭客户端
                        await client.aclose()
            
            if response.status_code != 200:
                if DEBUG_MODE:
                    logger.error(f"上游服务器错误: {response.status_code}")
                raise HTTPException(
                    status_code=response.status_code,
                    detail=response.text
                )
            
            if DEBUG_MODE:
                logger.info(f"非流式响应内容: {response.text}")
            
            # 在成功接收响应后
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("choices") and len(response_data["choices"]) > 0:
                    completion_text = response_data["choices"][0].get("message", {}).get("content", "")
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
            
            return Response(
                content=response.text,
                media_type="application/json"
            )
        
        if DEBUG_MODE:
            logger.info("使用流式响应")
        
        async def stream_generator():
            current_content = ""
            try:
                async with client.stream(
                    'POST',
                    upstream_url,
                    json={**body, "stream": True},
                    headers=headers,
                    timeout=60.0
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
                        if line.strip():
                            try:
                                if line.startswith('data: '):
                                    line = line.removeprefix('data: ')
                                if DEBUG_MODE == "Detail":
                                    logger.info(f"尝试解析的行内容: {line}")
                                data = json.loads(line)
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        content = delta["content"]
                                        current_content += content
                                        if DEBUG_MODE == "Detail":
                                            logger.info(f"流式响应内容: {content}")
                                        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode('utf-8')
                            except json.JSONDecodeError as e:
                                if DEBUG_MODE:
                                    logger.error(f"JSON解析错误: {str(e)}, 原始内容: {line}")
                                continue
                            except Exception as e:
                                if DEBUG_MODE:
                                    logger.error(f"处理流式响应时发生错误: {str(e)}")
                                continue
                    
                    # 在流式响应结束后记录完整的completion tokens
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
错误统计 [会话ID: {conversation_id}]
------------------------
- 模型: {model_name}
- 错误类型: {type(e).__name__}
- 错误信息: {str(e)}
- 提供商ID: {provider_id}
------------------------
""")
                # ... 错误处理代码 ...
            
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

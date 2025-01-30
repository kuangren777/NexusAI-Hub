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
                
        except Exception as e:
            print(f"错误详情: {str(e)}")
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
async def handle_chat_completions(request: Request, path_prefix: str = ""):
    try:
        # 获取Authorization header
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="缺少有效的Authorization header")
        
        personalized_key = auth_header.split(" ")[1]
        
        # 读取请求体
        body = await request.json()
        model_name = body.get("model")
        if not model_name:
            raise HTTPException(status_code=400, detail="缺少model参数")
        
        # 验证个性化密钥是否对应该模型的提供商
        provider_id = await verify_personalized_key(personalized_key, model_name)
        if not provider_id:
            raise HTTPException(status_code=401, detail="无效的API密钥或该密钥无权访问指定模型")
        
        # 获取提供商信息
        provider_info = get_provider_info(provider_id)
        if not provider_info:
            raise HTTPException(status_code=404, detail="提供商配置不存在")
        
        if model_name not in provider_info["models"]:
            raise HTTPException(status_code=400, detail="不支持的模型")
        
        # 生成或获取会话ID
        conversation_id = request.headers.get("X-Conversation-Id", str(uuid.uuid4()))
        
        # 改进 prompt tokens 的计算方法
        messages = body.get("messages", [])
        prompt_tokens = sum(len(str(msg.get("content", "")).encode('utf-8')) // 4 for msg in messages)
        
        await stats_tracker.record_chat(
            conversation_id=conversation_id,
            provider_id=provider_id,
            model_name=model_name,
            tokens_count=prompt_tokens,
            is_prompt=True
        )

        client = httpx.AsyncClient()
        
        async def stream_generator():
            completion_tokens = 0
            try:
                headers = {
                    "Authorization": f"Bearer {provider_info['server_key']}",
                    "Content-Type": "application/json"
                }
                
                # 确保开启流式响应
                body["stream"] = True
                
                # 构建上游URL，添加可选的path_prefix
                upstream_url = f"{provider_info['server_url'].rstrip('/')}{path_prefix}/chat/completions"
                
                async with client.stream(
                    'POST',
                    upstream_url,
                    json=body,
                    headers=headers,
                    timeout=30.0
                ) as response:
                    if response.status_code != 200:
                        error_msg = f"data: {{\"error\": \"上游服务器错误: {response.status_code}\"}}\n\n"
                        yield error_msg.encode('utf-8')
                        return

                    async for chunk in response.aiter_bytes():
                        try:
                            if chunk.startswith(b"data: "):
                                data = json.loads(chunk[6:])
                                if "choices" in data and data["choices"]:
                                    delta = data["choices"][0].get("delta", {})
                                    if "content" in delta:
                                        # 改进 completion tokens 的计算方法
                                        completion_tokens += len(delta["content"].encode('utf-8')) // 4
                        except:
                            pass
                        yield chunk
            except Exception as e:
                error_msg = f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                yield error_msg.encode('utf-8')
            finally:
                # 确保每次都记录 completion tokens
                if completion_tokens > 0:
                    await stats_tracker.record_chat(
                        conversation_id=conversation_id,
                        provider_id=provider_id,
                        model_name=model_name,
                        tokens_count=completion_tokens,
                        is_prompt=False
                    )
                await client.aclose()

        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "Transfer-Encoding": "chunked",
                "X-Accel-Buffering": "no",
                "X-Conversation-Id": conversation_id  # 返回会话ID给客户端
            }
        )

    except Exception as e:
        print(f"处理请求时发生错误: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
# API接口路由 (8002端口)
@app_api.post("/v1/chat/completions")
async def chat_completions_v1(request: Request):
    return await handle_chat_completions(request, "/v1")

@app_api.post("/chat/completions")
async def chat_completions(request: Request):
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

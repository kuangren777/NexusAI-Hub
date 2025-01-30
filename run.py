import uvicorn
import asyncio
from main import app_admin, app_api

async def run_admin():
    config = uvicorn.Config(app_admin, host="0.0.0.0", port=8000)
    server = uvicorn.Server(config)
    await server.serve()

async def run_api():
    config = uvicorn.Config(app_api, host="0.0.0.0", port=5231)
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    # 并发运行管理后台和API服务
    await asyncio.gather(
        run_admin(),
        run_api()
    )

if __name__ == "__main__":
    asyncio.run(main()) 
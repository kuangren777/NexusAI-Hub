import uvicorn
import asyncio
import signal
import sys
from main import app_admin, app_api
import logging
import multiprocessing
import os

# 获取CPU核心数
CPU_CORES = multiprocessing.cpu_count()
# 设置工作进程数，通常为CPU核心数的2-4倍
WORKERS_PER_APP = CPU_CORES * 2

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(process)d - %(message)s'
)
logger = logging.getLogger(__name__)

class GracefulExit:
    def __init__(self):
        self.shutdown = False
        self.servers = []
        # 根据不同平台注册信号处理器
        if sys.platform == 'win32':
            # Windows 平台只支持 SIGINT 和 SIGTERM
            signals = (signal.SIGINT, signal.SIGTERM)
        else:
            # Unix-like 平台支持更多信号
            signals = (
                signal.SIGTERM,  # 终止信号
                signal.SIGINT,   # 键盘中断（Ctrl+C）
                signal.SIGHUP,   # 终端断开
                signal.SIGQUIT   # 键盘退出
            )
        
        for sig in signals:
            try:
                if sys.platform == 'win32' and sig == signal.SIGTERM:
                    # Windows下跳过SIGTERM的注册
                    continue
                signal.signal(sig, self._signal_handler)
            except (ValueError, AttributeError) as e:
                logger.warning(f"无法注册信号 {sig}: {str(e)}")

    def _signal_handler(self, signum, frame):
        """信号处理函数"""
        sig_name = signal.Signals(signum).name
        logger.info(f"收到 {sig_name} 信号，开始优雅关闭...")
        self.shutdown = True
        # 关闭所有服务器
        for server in self.servers:
            if not server.should_exit:
                server.should_exit = True

    def add_server(self, server):
        """添加服务器实例到管理列表"""
        self.servers.append(server)

async def run_admin(exit_handler):
    """运行管理后台服务"""
    config = uvicorn.Config(
        app_admin,
        host="0.0.0.0",
        port=8000,
        workers=WORKERS_PER_APP,  # 使用多进程
        loop="uvicorn.loops.auto",  # 自动选择最佳事件循环
        http="httptools",  # 使用更快的HTTP解析器
        log_level="info",
        limit_concurrency=1000,  # 限制并发连接数
        limit_max_requests=50000,  # 限制最大请求数
        timeout_keep_alive=30,  # 保持连接超时时间
        access_log=True,
        proxy_headers=True,  # 支持代理头
        forwarded_allow_ips="*",  # 允许所有转发IP
    )
    server = uvicorn.Server(config)
    exit_handler.add_server(server)
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"管理后台服务发生错误: {str(e)}")
        raise

async def run_api(exit_handler):
    """运行 API 服务"""
    config = uvicorn.Config(
        app_api,
        host="0.0.0.0",
        port=5231,
        workers=WORKERS_PER_APP,  # 使用多进程
        loop="uvicorn.loops.auto",  # 自动选择最佳事件循环
        http="httptools",  # 使用更快的HTTP解析器
        log_level="info",
        limit_concurrency=1000,  # 限制并发连接数
        limit_max_requests=50000,  # 限制最大请求数
        timeout_keep_alive=30,  # 保持连接超时时间
        access_log=True,
        proxy_headers=True,  # 支持代理头
        forwarded_allow_ips="*",  # 允许所有转发IP
    )
    server = uvicorn.Server(config)
    exit_handler.add_server(server)
    try:
        await server.serve()
    except Exception as e:
        logger.error(f"API 服务发生错误: {str(e)}")
        raise

async def cleanup():
    """清理资源"""
    logger.info("执行清理操作...")
    # 这里可以添加其他需要清理的资源
    # 例如关闭数据库连接、清理临时文件等
    await asyncio.sleep(0.1)  # 给一些时间让日志输出
    logger.info("清理完成")

async def main():
    """主函数"""
    # 设置进程标题
    try:
        import setproctitle
        setproctitle.setproctitle('llm_key_server')
    except ImportError:
        pass

    # 设置ulimit（仅在Unix系统上）
    if sys.platform != 'win32':
        import resource
        # 设置最大文件描述符数量
        resource.setrlimit(resource.RLIMIT_NOFILE, (65535, 65535))

    exit_handler = GracefulExit()
    
    try:
        # 并发运行管理后台和API服务
        await asyncio.gather(
            run_admin(exit_handler),
            run_api(exit_handler)
        )
    except Exception as e:
        logger.error(f"服务运行出错: {str(e)}")
    finally:
        if exit_handler.shutdown:
            logger.info("正在关闭服务...")
            await cleanup()
        else:
            logger.error("服务异常终止")
            await cleanup()

if __name__ == "__main__":
    try:
        # 设置多进程启动方法
        if sys.platform == 'win32':
            # Windows 平台使用 spawn
            multiprocessing.set_start_method('spawn')
        else:
            # Unix-like 平台使用 fork
            multiprocessing.set_start_method('fork')

        # 平台特定的事件循环设置
        if sys.platform == 'win32':
            # Windows 平台使用 ProactorEventLoop
            loop = asyncio.ProactorEventLoop()
            asyncio.set_event_loop(loop)
        else:
            # Unix-like 平台使用默认的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 在 Unix-like 平台上设置子进程信号处理
            loop.add_signal_handler(signal.SIGCHLD, lambda: None)
        
        # 运行主程序
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序发生未预期的错误: {str(e)}")
        sys.exit(1)
    finally:
        logger.info("程序退出")
        sys.exit(0) 
import asyncio
import json
from pathlib import Path
import logging
from datetime import datetime
import httpx  # Use httpx for async HTTP requests
import argparse
import sqlite3

# Set up logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
log_file = LOG_DIR / f"model_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Database path
DATABASE_PATH = Path("data/config.db")

async def test_model(provider_id: int, model_name: str, personalized_key: str, port: int):
    """Test a single model"""
    logger.info(f"\n开始测试模型: {model_name}")
    logger.info("=" * 50)

    metrics = {
        "first_response_time": None,
        "total_tokens": 0,
        "total_time": 0,
        "supports_stream": False
    }

    base_url = f"http://localhost:{port}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {personalized_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient(timeout=30.0) as client:  # 添加超时设置
        # Test stream response
        try:
            stream_request_body = {
                "model": model_name,
                "messages": [{"role": "user", "content": "你是谁"}],
                "stream": True
            }
            
            start_time = datetime.now()
            stream_response = await client.post(base_url, json=stream_request_body, headers=headers)
            
            if stream_response.status_code == 200 and 'text/event-stream' in stream_response.headers.get('Content-Type', ''):
                metrics["supports_stream"] = True
                logger.info("Stream response supported, starting to receive data...")

                async for line in stream_response.aiter_lines():
                    if line.strip():
                        try:
                            if line.startswith('data: '):
                                line = line[6:].strip()
                                if line != '[DONE]':
                                    data = json.loads(line)
                                    if "choices" in data and data["choices"]:
                                        delta = data["choices"][0].get("delta", {})
                                        if "content" in delta:
                                            content = delta["content"]
                                            tokens = len(content.encode('utf-8')) // 4
                                            metrics["total_tokens"] += tokens
                                            logger.info(f"Stream response content: {content}")
                        except json.JSONDecodeError as e:
                            logger.error(f"JSON parsing error: {str(e)}, raw content: {line}")
                        except Exception as e:
                            logger.error(f"Error processing stream response: {str(e)}")

        except Exception as e:
            metrics["supports_stream"] = False
            logger.error(f"Stream response test failed: {str(e)}")

        # Test regular response
        try:
            request_body = {
                "model": model_name,
                "messages": [{"role": "user", "content": "请写一段100字的文章"}],
                "stream": False
            }

            logger.info(f"Request body: {json.dumps(request_body, ensure_ascii=False, indent=2)}")
            
            start_time = datetime.now()
            response = await client.post(base_url, json=request_body, headers=headers)
            first_response_time = (datetime.now() - start_time).total_seconds()
            metrics["first_response_time"] = first_response_time

            if response.status_code != 200:
                error_text = response.text
                raise Exception(f"Request failed with status: {response.status_code}, Error: {error_text}")
            
            content = response.json()
            
            total_time = (datetime.now() - start_time).total_seconds()
            response_text = content.get('choices', [{}])[0].get('message', {}).get('content', '')
            total_tokens = len(response_text.encode('utf-8')) // 4  # 更准确的token估算
            
            metrics["total_time"] = total_time
            metrics["total_tokens"] += total_tokens

            logger.info("Request succeeded!")
            logger.info(f"Response content: {json.dumps(content, ensure_ascii=False, indent=2)}")

            return {
                "provider_id": provider_id,
                "model_name": model_name,
                "success": True,
                "response": content,
                "metrics": metrics
            }

        except Exception as e:
            error_msg = str(e)
            if not error_msg:
                error_msg = "Unknown error occurred"
            logger.error(f"Error during testing: {error_msg}")
            return {
                "provider_id": provider_id,
                "model_name": model_name,
                "success": False,
                "error": error_msg,
                "metrics": metrics
            }


async def test_all_models(skip_ip_test=True, port=5231):
    """测试所有模型
    Args:
        skip_ip_test (bool): 是否跳过IP地址形式的服务器测试
        port (int): 本地转发服务器的端口号，默认5231
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT 
                sp.id,
                sp.name,
                sp.personalized_key,
                pm.model_name,
                sp.server_url
            FROM service_providers sp
            JOIN provider_models pm ON sp.id = pm.provider_id
        """)
        
        models = cursor.fetchall()
        
        if not models:
            logger.warning("数据库中没有找到任何模型配置")
            return []

        results = []
        base_url = f"http://localhost:{port}"
        logger.info(f"使用本地转发服务器: {base_url}")

        for provider_id, provider_name, personalized_key, model_name, server_url in models:
            # 检查是否需要跳过IP地址形式的服务器
            if skip_ip_test and server_url and all(part.replace('.', '').isdigit() for part in server_url.split('://')[-1].split(':')[0].split('.')):
                logger.info(f"\n跳过IP地址服务器的测试: {provider_name} - {model_name} ({server_url})")
                continue

            logger.info(f"\n测试提供商 {provider_name} 的模型 {model_name}")
            logger.info(f"目标服务器: {server_url}")
            result = await test_model(provider_id, model_name, personalized_key, port)
            result['provider_name'] = provider_name
            result['server_url'] = server_url
            results.append(result)

        return results

    except sqlite3.Error as e:
        logger.error(f"数据库错误: {str(e)}")
        return []
    finally:
        conn.close()

def save_results(results):
    """保存测试结果到文件"""
    output_file = Path("test_results") / f"model_test_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.parent.mkdir(exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n测试结果已保存到: {output_file}")

def print_summary(results):
    """打印测试总结"""
    logger.info("\n测试总结")
    logger.info("=" * 50)
    total = len(results)
    successful = sum(1 for r in results if r['success'])
    logger.info(f"总计测试模型数: {total}")
    logger.info(f"成功数量: {successful}")
    logger.info(f"失败数量: {total - successful}")
    
    logger.info("\n模型性能指标:")
    logger.info("-" * 30)
    
    for result in results:
        if result['success']:
            metrics = result['metrics']
            tokens_per_second = metrics['total_tokens'] / metrics['total_time'] if metrics['total_time'] > 0 else 0
            
            logger.info(f"\n供应商: {result['provider_name']}")
            logger.info(f"模型名称: {result['model_name']}")
            logger.info(f"原始服务器: {result['server_url']}")
            logger.info(f"平均处理速度: {tokens_per_second:.2f} tokens/秒")
            logger.info(f"总生成tokens: {metrics['total_tokens']:.0f}")
            logger.info(f"总响应时间: {metrics['total_time']:.2f} 秒")
    
    if total - successful > 0:
        logger.info("\n失败的模型详情:")
        for result in results:
            if not result['success']:
                logger.info(f"\n供应商: {result['provider_name']}")
                logger.info(f"模型名称: {result['model_name']}")
                logger.info(f"原始服务器: {result['server_url']}")
                logger.info(f"错误信息: {result.get('error', '未知错误')}")
                logger.info("-" * 30)

async def main():
    parser = argparse.ArgumentParser(description='模型测试工具')
    parser.add_argument('--port', type=int, default=5231, help='本地转发服务器端口号')
    parser.add_argument('--test-all', action='store_false', dest='skip_ip_test',
                       help='测试所有服务器（包括IP地址形式的服务器）')
    args = parser.parse_args()

    logger.info(f"开始模型测试... 使用本地转发端口: {args.port}")
    logger.info(f"{'跳过' if args.skip_ip_test else '包含'} IP地址服务器测试")
    
    results = await test_all_models(skip_ip_test=args.skip_ip_test, port=args.port)
    save_results(results)
    print_summary(results)

if __name__ == "__main__":
    asyncio.run(main())

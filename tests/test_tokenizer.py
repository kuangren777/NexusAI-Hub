import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from my_tokenizer import Tokenizer
import pytest
import json
from unittest.mock import patch, AsyncMock
from config.tokenizer_config import TOKENIZER_MODEL_ID

@pytest.fixture
def tokenizer():
    return Tokenizer()

@pytest.fixture
def mock_response():
    return {
        "object": "list",
        "id": "021718067849899d92fcbe0865fdffdde",
        "model": "doubao-pro-32k-240615",
        "data": [{
            "object": "tokenization",
            "index": 0,
            "total_tokens": 4,
            "token_ids": [14539, 4752, 5189, 5399],
            "offset_mapping": [[0, 2], [2, 5], [5, 7], [7, 8]]
        }],
        "created": 1724902147
    }

@pytest.mark.asyncio
async def test_count_tokens_success(tokenizer, mock_response):
    # 模拟成功的API响应
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response
        )
        
        result = await tokenizer.count_tokens("天空为什么这么蓝", TOKENIZER_MODEL_ID)
        assert result == 4
        
        # 验证API调用参数
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert json.loads(call_kwargs['json']['text'][0]) == "天空为什么这么蓝"
        assert call_kwargs['json']['model'] == TOKENIZER_MODEL_ID

@pytest.mark.asyncio
async def test_count_tokens_api_error(tokenizer):
    # 模拟API错误
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=500,
            text="Internal Server Error"
        )
        
        text = "测试文本"
        result = await tokenizer.count_tokens(text, TOKENIZER_MODEL_ID)
        # 验证降级方案是否正确工作
        assert result == len(text.encode('utf-8')) // 4

@pytest.mark.asyncio
async def test_count_messages_tokens(tokenizer, mock_response):
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "很高兴见到你"}
    ]
    
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response
        )
        
        result = await tokenizer.count_messages_tokens(messages, TOKENIZER_MODEL_ID)
        assert result == 8  # 每条消息4个token

@pytest.mark.asyncio
async def test_get_token_info_success(tokenizer, mock_response):
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: mock_response
        )
        
        result = await tokenizer.get_token_info("天空为什么这么蓝", TOKENIZER_MODEL_ID)
        assert result is not None
        assert "token_ids" in result
        assert "offset_mapping" in result
        assert "total_tokens" in result
        assert result["token_ids"] == [14539, 4752, 5189, 5399]

@pytest.mark.asyncio
async def test_get_token_info_failure(tokenizer):
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=500,
            text="Internal Server Error"
        )
        
        result = await tokenizer.get_token_info("测试文本", TOKENIZER_MODEL_ID)
        assert result is None

@pytest.mark.asyncio
async def test_error_handling(tokenizer):
    # 模拟网络异常
    with patch('httpx.AsyncClient.post', side_effect=Exception("Network Error")):
        result = await tokenizer.count_tokens("测试文本", TOKENIZER_MODEL_ID)
        # 验证降级方案
        assert result == len("测试文本".encode('utf-8')) // 4

@pytest.mark.asyncio
async def test_empty_response(tokenizer):
    # 模拟空响应
    with patch('httpx.AsyncClient.post') as mock_post:
        mock_post.return_value = AsyncMock(
            status_code=200,
            json=lambda: {"data": []}
        )
        
        text = "测试文本"
        result = await tokenizer.count_tokens(text, TOKENIZER_MODEL_ID)
        # 验证降级方案
        assert result == len(text.encode('utf-8')) // 4 
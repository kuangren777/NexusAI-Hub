import httpx
import json
from typing import List, Dict, Any, Tuple, Optional
import logging
from config.tokenizer_config import TOKENIZER_API_KEY, TOKENIZER_API_URL, TOKENIZER_MODEL_ID

class Tokenizer:
    def __init__(self, api_url: str = TOKENIZER_API_URL, api_key: str = TOKENIZER_API_KEY):
        self.api_url = api_url
        self.api_key = api_key
        self.model_id = TOKENIZER_MODEL_ID
        self.logger = logging.getLogger('nexusai.tokenizer')

    async def count_tokens(self, text: str, provider_key: str = None) -> int:
        """
        计算文本的token数量
        
        Args:
            text: 需要计算token的文本
            provider_key: 提供商的API密钥（可选，默认使用tokenizer自己的密钥）
        
        Returns:
            int: token数量
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                payload = {
                    "model": self.model_id,
                    "text": [text]
                }
                
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data") and len(result["data"]) > 0:
                        return result["data"][0]["total_tokens"]
                    
                self.logger.error(f"Token计算API返回错误: {response.text}")
                return len(text.encode('utf-8')) // 4  # 降级方案：使用简单的字节长度估算
                
        except Exception as e:
            self.logger.error(f"计算token时发生错误: {str(e)}")
            return len(text.encode('utf-8')) // 4  # 降级方案
    
    async def count_messages_tokens(self, messages: List[Dict[str, str]], provider_key: str = None) -> int:
        """
        计算消息列表中所有文本的总token数量
        
        Args:
            messages: 消息列表
            provider_key: 提供商的API密钥（可选，默认使用tokenizer自己的密钥）
        
        Returns:
            int: 总token数量
        """
        total_tokens = 0
        for message in messages:
            content = message.get("content", "")
            if content:
                tokens = await self.count_tokens(content, provider_key)
                total_tokens += tokens
        return total_tokens

    async def get_token_info(self, text: str, provider_key: str = None) -> Optional[Dict[str, Any]]:
        """
        获取文本的详细token信息
        
        Args:
            text: 需要分析的文本
            provider_key: 提供商的API密钥（可选，默认使用tokenizer自己的密钥）
        
        Returns:
            Dict: 包含token_ids和offset_mapping的字典，如果发生错误则返回None
        """
        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                }
                
                payload = {
                    "model": self.model_id,
                    "text": [text]
                }
                
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers
                )
                
                if response.status_code == 200:
                    result = response.json()
                    if result.get("data") and len(result["data"]) > 0:
                        token_data = result["data"][0]
                        return {
                            "token_ids": token_data["token_ids"],
                            "offset_mapping": token_data["offset_mapping"],
                            "total_tokens": token_data["total_tokens"]
                        }
                
                self.logger.error(f"Token信息API返回错误: {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"获取token信息时发生错误: {str(e)}")
            return None 
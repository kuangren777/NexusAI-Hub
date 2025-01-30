import json
from datetime import datetime
import aiosqlite
from pathlib import Path
import re

class StatsTracker:
    def __init__(self, db_path="data/stats.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.setup_db()
        self._tokenizers = {}
        # 添加快速估算的比率
        self.tokens_ratio = {
            'zh': 1.7,  # 中文字符平均约1.7个token
            'en': 0.25  # 英文单词平均约0.25个token
        }

    def setup_db(self):
        # 同步方式初始化数据库
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    provider_id INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    tokens_count INTEGER NOT NULL,
                    is_prompt BOOLEAN NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_id 
                ON chat_stats(conversation_id)
            """)

    async def record_chat(self, conversation_id: str, provider_id: int, 
                         model_name: str, tokens_count: int, is_prompt: bool):
        try:
            print(f"Recording chat stats: conversation_id={conversation_id}, "
                  f"tokens={tokens_count}, is_prompt={is_prompt}")  # 添加日志
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO chat_stats 
                    (timestamp, conversation_id, provider_id, model_name, tokens_count, is_prompt)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), conversation_id, provider_id, 
                     model_name, tokens_count, is_prompt))
                await db.commit()
        except Exception as e:
            print(f"Error recording chat stats: {e}")  # 添加错误日志

    async def get_conversation_stats(self, conversation_id: str):
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT 
                    COUNT(*) as rounds,
                    SUM(CASE WHEN is_prompt = 1 THEN tokens_count ELSE 0 END) as prompt_tokens,
                    SUM(CASE WHEN is_prompt = 0 THEN tokens_count ELSE 0 END) as completion_tokens,
                    SUM(tokens_count) as total_tokens
                FROM chat_stats 
                WHERE conversation_id = ?
            """, (conversation_id,)) as cursor:
                row = await cursor.fetchone()
                return {
                    "conversation_id": conversation_id,
                    "rounds": row[0],
                    "prompt_tokens": row[1] or 0,
                    "completion_tokens": row[2] or 0,
                    "total_tokens": row[3] or 0
                }

    async def get_total_stats(self):
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 修改 SQL 查询以分别统计 prompt 和 completion tokens
                async with db.execute("""
                    SELECT 
                        COUNT(DISTINCT conversation_id) as total_conversations,
                        COUNT(*) / 2 as total_rounds,  -- 除以2因为每轮对话包含prompt和completion
                        SUM(CASE WHEN is_prompt = 1 THEN tokens_count ELSE 0 END) as prompt_tokens,
                        SUM(CASE WHEN is_prompt = 0 THEN tokens_count ELSE 0 END) as completion_tokens,
                        SUM(tokens_count) as total_tokens
                    FROM chat_stats
                """) as cursor:
                    row = await cursor.fetchone()
                    stats = {
                        "total_conversations": row[0],
                        "total_rounds": row[1],
                        "prompt_tokens": row[2] or 0,
                        "completion_tokens": row[3] or 0,
                        "total_tokens": row[4] or 0
                    }
                    print(f"Total stats: {stats}")  # 添加日志
                    return stats
        except Exception as e:
            print(f"Error getting total stats: {e}")  # 添加错误日志
            return {
                "total_conversations": 0,
                "total_rounds": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }

    def estimate_tokens(self, text: str) -> int:
        """
        快速估算token数量
        - 中文按字符计算
        - 英文按空格分词
        """
        # 分离中英文
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))
        english_words = len(re.findall(r'[a-zA-Z]+', text))
        
        # 估算token数
        estimated_tokens = (
            chinese_chars * self.tokens_ratio['zh'] +
            english_words * self.tokens_ratio['en']
        )
        
        return int(estimated_tokens)

    def count_tokens(self, text: str, model_name: str, use_estimation: bool = True) -> int:
        """
        计算token数量
        :param text: 要计算的文本
        :param model_name: 模型名称
        :param use_estimation: 是否使用估算方法
        """
        if use_estimation:
            return self.estimate_tokens(text)
        
        return len(self._tokenizers[model_name].encode(text))

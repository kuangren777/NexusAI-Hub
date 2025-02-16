import json
from datetime import datetime
import aiosqlite
from pathlib import Path
from my_tokenizer import Tokenizer

class StatsTracker:
    def __init__(self, db_path="data/stats.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.setup_db()
        self.tokenizer = Tokenizer()  # 初始化tokenizer

    def setup_db(self):
        # 同步方式初始化数据库
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            # 原有的token统计表
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
            
            # 聊天记录表
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    conversation_id TEXT NOT NULL,
                    provider_id INTEGER NOT NULL,
                    model_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tokens_count INTEGER NOT NULL
                )
            """)
            
            # 创建索引
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_conversation_id 
                ON chat_stats(conversation_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_id 
                ON chat_messages(conversation_id)
            """)

    async def record_chat(self, conversation_id: str, provider_id: int, 
                         model_name: str, tokens_count: int, is_prompt: bool, 
                         message: str = ""):
        try:
            # 使用tokenizer计算token数量
            if message:
                tokens_count = await self.tokenizer.count_tokens(message)
                
            async with aiosqlite.connect(self.db_path) as db:
                # 记录token统计
                await db.execute("""
                    INSERT INTO chat_stats 
                    (timestamp, conversation_id, provider_id, model_name, tokens_count, is_prompt)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (datetime.now().isoformat(), conversation_id, provider_id, 
                     model_name, tokens_count, is_prompt))
                
                # 记录聊天消息
                if message:
                    await db.execute("""
                        INSERT INTO chat_messages 
                        (timestamp, conversation_id, provider_id, model_name, role, content, tokens_count)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        datetime.now().isoformat(),
                        conversation_id,
                        provider_id,
                        model_name,
                        "user" if is_prompt else "assistant",
                        message,
                        tokens_count
                    ))
                
                await db.commit()
        except Exception as e:
            print(f"Error recording chat: {e}")

    async def get_conversation_messages(self, conversation_id: str):
        """获取指定会话的完整聊天记录"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("""
                SELECT timestamp, role, content, tokens_count
                FROM chat_messages 
                WHERE conversation_id = ?
                ORDER BY timestamp ASC
            """, (conversation_id,)) as cursor:
                messages = await cursor.fetchall()
                return [{
                    "timestamp": msg[0],
                    "role": msg[1],
                    "content": msg[2],
                    "tokens_count": msg[3]
                } for msg in messages]

    async def get_conversation_stats(self, conversation_id: str):
        """获取会话统计信息，包含消息记录"""
        async with aiosqlite.connect(self.db_path) as db:
            # 获取token统计
            async with db.execute("""
                SELECT 
                    COUNT(*) as rounds,
                    SUM(CASE WHEN is_prompt = 1 THEN tokens_count ELSE 0 END) as prompt_tokens,
                    SUM(CASE WHEN is_prompt = 0 THEN tokens_count ELSE 0 END) as completion_tokens,
                    SUM(tokens_count) as total_tokens
                FROM chat_stats 
                WHERE conversation_id = ?
            """, (conversation_id,)) as cursor:
                stats = await cursor.fetchone()
                
            # 获取聊天记录
            messages = await self.get_conversation_messages(conversation_id)
                
            return {
                "conversation_id": conversation_id,
                "rounds": stats[0],
                "prompt_tokens": stats[1] or 0,
                "completion_tokens": stats[2] or 0,
                "total_tokens": stats[3] or 0,
                "messages": messages
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

    async def get_last_conversation(self, content: str, time_window_minutes: int = 30):
        """
        根据消息内容查找最近的相关会话
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                time_limit = (datetime.now() - 
                            datetime.timedelta(minutes=time_window_minutes)).isoformat()
                
                # 1. 首先尝试完全匹配
                async with db.execute("""
                    SELECT DISTINCT conversation_id, timestamp
                    FROM chat_messages
                    WHERE timestamp > ?
                    AND role = 'user'
                    AND content = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                """, (time_limit, content)) as cursor:
                    result = await cursor.fetchone()
                    if result:
                        return {
                            "conversation_id": result[0],
                            "timestamp": result[1]
                        }
                
                # 2. 如果没有完全匹配，尝试关键词匹配
                # 提取内容的前20个字符作为关键词
                if len(content) > 20:
                    keyword = content[:20]
                    async with db.execute("""
                        SELECT DISTINCT conversation_id, timestamp
                        FROM chat_messages
                        WHERE timestamp > ?
                        AND role = 'user'
                        AND content LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT 1
                    """, (time_limit, f"{keyword}%")) as cursor:
                        result = await cursor.fetchone()
                        if result:
                            return {
                                "conversation_id": result[0],
                                "timestamp": result[1]
                            }
                
                return None
                    
        except Exception as e:
            print(f"Error finding conversation: {e}")
            return None

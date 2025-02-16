import requests
from PyPDF2 import PdfReader
import json
import numpy as np
from typing import List, Dict, Tuple
from sklearn.metrics.pairwise import cosine_similarity

class PDFEmbedding:
    def __init__(self, embedding_url: str, embedding_api_key: str, 
                 chat_url: str, chat_api_key: str,
                 embedding_model: str, chat_model: str):
        # 嵌入API的配置
        self.embedding_api_key = embedding_api_key
        self.embedding_headers = {
            "Authorization": f"Bearer {embedding_api_key}",
            "Content-Type": "application/json"
        }
        self.embedding_url = embedding_url
        self.embedding_model = embedding_model

        # Chat API的配置
        self.chat_api_key = chat_api_key
        self.chat_headers = {
            "Authorization": f"Bearer {chat_api_key}",
            "Content-Type": "application/json"
        }
        self.chat_url = chat_url
        self.chat_model = chat_model

        self.chunks = []
        self.embeddings = []
    
    def read_pdf(self, pdf_path: str) -> str:
        """读取PDF文件并提取文本"""
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    
    def create_chunks(self, text: str, chunk_size: int = 1000) -> List[str]:
        """将文本分割成较小的块"""
        words = text.split()
        chunks = []
        current_chunk = []
        current_size = 0
        
        for word in words:
            current_chunk.append(word)
            current_size += len(word) + 1
            if current_size >= chunk_size:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_size = 0
        
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def get_embeddings(self, text_chunks: List[str]) -> List[List[float]]:
        """使用Embedding API生成文本嵌入向量"""
        embeddings = []
        for chunk in text_chunks:
            payload = {
                "model": self.embedding_model,
                "input": chunk
            }
            
            response = requests.post(
                self.embedding_url,
                headers=self.embedding_headers,  # 使用embedding专用的headers
                json=payload
            )
            
            if response.status_code == 200:
                result = response.json()
                embeddings.append(result['data'][0]['embedding'])
            else:
                raise Exception(f"API调用失败: {response.status_code}, {response.text}")
                
        return embeddings
    
    def save_embeddings(self, embeddings: List[List[float]], file_path: str):
        """将嵌入向量保存到文件"""
        with open(file_path, 'w') as f:
            json.dump(embeddings, f)
    
    def process_pdf(self, pdf_path: str, output_path: str):
        """处理PDF文件的完整流程"""
        # 读取PDF
        text = self.read_pdf(pdf_path)
        
        # 分块
        self.chunks = self.create_chunks(text)
        
        # 生成嵌入向量
        self.embeddings = self.get_embeddings(self.chunks)
        
        # 保存结果
        self.save_embeddings(self.embeddings, output_path)
        
        return self.embeddings

    def get_question_embedding(self, question: str) -> List[float]:
        """获取问题的embedding"""
        payload = {
            "model": self.embedding_model,
            "input": question
        }
        
        response = requests.post(
            self.embedding_url,
            headers=self.embedding_headers,  # 使用embedding专用的headers
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['data'][0]['embedding']
        else:
            raise Exception(f"API调用失败: {response.status_code}, {response.text}")

    def find_relevant_chunks(self, question_embedding: List[float], top_k: int = 3) -> List[Tuple[str, float]]:
        """找到最相关的文本块"""
        # 计算问题embedding与所有文档块embedding的相似度
        similarities = cosine_similarity(
            [question_embedding],
            self.embeddings
        )[0]
        
        # 获取最相关的文本块索引
        most_relevant_indices = np.argsort(similarities)[-top_k:][::-1]
        
        # 返回最相关的文本块及其相似度
        return [(self.chunks[i], similarities[i]) for i in most_relevant_indices]

    def chat_completion(self, messages: List[Dict]) -> str:
        """调用ChatGPT进行对话"""
        payload = {
            "model": self.chat_model,
            "messages": messages,
            "temperature": 0.7
        }
        
        response = requests.post(
            self.chat_url,
            headers=self.chat_headers,  # 使用chat专用的headers
            json=payload
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API调用失败: {response.status_code}, {response.text}")

    def answer_question(self, question: str) -> str:
        """回答问题的完整流程"""
        # 获取问题的embedding
        question_embedding = self.get_question_embedding(question)
        
        # 找到相关的文本块
        relevant_chunks = self.find_relevant_chunks(question_embedding)
        
        # 构建提示信息
        context = "\n".join([chunk for chunk, _ in relevant_chunks])
        messages = [
            {"role": "system", "content": "你是一个专业的助手。请基于提供的上下文信息回答用户的问题。如果无法从上下文中找到答案，请说明。"},
            {"role": "user", "content": f"上下文信息：\n{context}\n\n问题：{question}"}
        ]
        
        # 获取回答
        answer = self.chat_completion(messages)
        return answer

# 使用示例
if __name__ == "__main__":
    # API配置
    embedding_api_key = "sk-jqbfbbypkqogtlaaeyuefolvvwprknojgcrdinzlwwzjseps"
    chat_api_key = "kuangren777"
    embedding_url = "https://api.siliconflow.cn/v1/embeddings"
    chat_url = "https://kr777.top/v1/chat/completions"
    
    # 模型配置
    embedding_model = "BAAI/bge-m3"
    chat_model = "deepseek-ai/DeepSeek-R1"
    
    pdf_processor = PDFEmbedding(
        embedding_url=embedding_url,
        embedding_api_key=embedding_api_key,
        chat_url=chat_url,
        chat_api_key=chat_api_key,
        embedding_model=embedding_model,
        chat_model=chat_model
    )
    
    # 处理PDF文件
    pdf_processor.process_pdf(
        pdf_path="embedding/test.pdf",
        output_path="embedding/embeddings.json"
    )
    
    # 进行对话
    while True:
        question = input("\n请输入您的问题（输入'q'结束对话）：")
        if question == 'q':
            break
            
        try:
            answer = pdf_processor.answer_question(question)
            print(f"\n回答：{answer}")
        except Exception as e:
            print(f"发生错误：{str(e)}")

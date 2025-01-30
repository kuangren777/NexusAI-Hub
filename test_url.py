import requests
import json

class ChatTest:
    def __init__(self, base_url, model_name, api_key=None):
        self.base_url = base_url.rstrip('/')  # 移除URL末尾的斜杠
        self.model_name = model_name
        self.headers = {
            "Content-Type": "application/json"
        }
        # 如果提供了 API Key，添加到请求头中
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        
    def chat(self, message, temperature=0.7):
        """
        与模型进行对话
        :param message: 用户输入的消息
        :param temperature: 温度参数，控制响应的随机性
        :return: 模型的响应
        """
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "user", "content": message}
            ],
            "temperature": temperature
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",  # 添加 v1 路径
                headers=self.headers,
                json=payload,
                timeout=30  # 添加超时设置
            )
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except requests.exceptions.RequestException as e:
            return f"请求错误: {str(e)}"
        except (KeyError, json.JSONDecodeError) as e:
            return f"响应解析错误: {str(e)}"

def main():
    # 使用示例
    url = "https://kr-gemini.deno.dev"  # 替换为你的API端点
    model = "gemini-2.0-flash-exp"  # 替换为你要使用的模型名称
    api_key = "AIzaSyDbWBlTpGPB2L3c6kEh_vgFEoqjMzBcA70"  # 替换为你的 API Key
    
    chat_test = ChatTest(url, model, api_key)
    
    while True:
        user_input = input("请输入你的问题 (输入 'quit' 退出): ")
        if user_input.lower() == 'quit':
            break
            
        response = chat_test.chat(user_input)
        print(f"\n模型响应: {response}\n")

if __name__ == "__main__":
    main()

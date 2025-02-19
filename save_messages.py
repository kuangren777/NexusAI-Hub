from pathlib import Path
from datetime import datetime, timedelta
import json

def get_china_time():
    """获取UTC+8时区的中国时间"""
    utc_now = datetime.utcnow()
    return utc_now + timedelta(hours=8)

def save_message_to_file(data: dict):
    """保存消息到文件系统（使用中国时间）"""
    try:
        # 获取中国时间
        china_now = get_china_time()
        
        # 构建目录路径 messages/年/月/日/小时
        dir_path = Path("messages") / f"{china_now.year}" / \
            f"{china_now.month:02d}" / f"{china_now.day:02d}" / \
            f"{china_now.hour:02d}"
        dir_path.mkdir(parents=True, exist_ok=True)
        
        # 构建文件名 messages_年月日-时分.json
        filename = f"messages_{china_now.strftime('%Y%m%d-%H%M')}.json"
        file_path = dir_path / filename
        
        # 如果文件已存在则追加，否则创建新文件
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
                if not isinstance(existing_data, list):
                    existing_data = [existing_data]
            existing_data.append(data)
        else:
            existing_data = [data]
        
        # 写入文件
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(existing_data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"保存消息时出错: {str(e)}")

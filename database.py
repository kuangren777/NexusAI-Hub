import sqlite3
from pathlib import Path

# 使用相对路径存储数据库文件
DATABASE_PATH = Path("data/config.db")

# 初始化数据库
def init_db():
    """初始化数据库"""
    # 确保父目录存在
    DATABASE_PATH.parent.mkdir(exist_ok=True)
    
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    
    # 创建服务提供商表（移除personalized_key的UNIQUE约束）
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS service_providers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        server_url TEXT NOT NULL,
        server_key TEXT NOT NULL,
        personalized_key TEXT NOT NULL,
        description TEXT
    )
    ''')
    
    # 创建提供商模型表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS provider_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id INTEGER NOT NULL,
        model_name TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY (provider_id) REFERENCES service_providers (id),
        UNIQUE(provider_id, model_name)
    )
    ''')
    
    conn.commit()
    conn.close()

# 服务提供商相关操作
def add_service_provider(name: str, server_url: str, server_key: str, personalized_key: str, description: str = ""):
    print(f"添加服务提供商: name={name}, url={server_url}")
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO service_providers 
               (name, server_url, server_key, personalized_key, description) 
               VALUES (?, ?, ?, ?, ?)""",
            (name, server_url, server_key, personalized_key, description)
        )
        conn.commit()
        return cursor.lastrowid
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def add_provider_model(provider_id: int, model_name: str, description: str = ""):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """INSERT INTO provider_models 
               (provider_id, model_name, description) 
               VALUES (?, ?, ?)""",
            (provider_id, model_name, description)
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        raise Exception("该提供商已存在此模型")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_all_providers():
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM service_providers")
    providers = cursor.fetchall()
    conn.close()
    return providers

def get_models_by_provider(provider_id: int):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, provider_id, model_name, description 
               FROM provider_models 
               WHERE provider_id = ?
               ORDER BY id""", 
            (provider_id,)
        )
        models = cursor.fetchall()
        return models
    finally:
        conn.close()

def get_provider_info(provider_id: int):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        # 首先获取提供商基本信息
        cursor.execute(
            """SELECT sp.server_url, sp.server_key 
               FROM service_providers sp
               WHERE sp.id = ?""",
            (provider_id,)
        )
        provider_result = cursor.fetchone()
        
        if not provider_result:
            return None
            
        # 然后获取该提供商的所有模型
        cursor.execute(
            """SELECT model_name 
               FROM provider_models 
               WHERE provider_id = ?""",
            (provider_id,)
        )
        models = cursor.fetchall()
        
        return {
            "server_url": provider_result[0],
            "server_key": provider_result[1],
            "models": [model[0] for model in models]  # 返回所有模型名称列表
        }
    finally:
        conn.close()

# 添加删除函数
def delete_provider(provider_id: int):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        # 首先删除关联的模型
        cursor.execute("DELETE FROM provider_models WHERE provider_id = ?", (provider_id,))
        # 然后删除提供商
        cursor.execute("DELETE FROM service_providers WHERE id = ?", (provider_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# 添加更新函数
def update_provider(provider_id: int, name: str, server_url: str, server_key: str, personalized_key: str, description: str = ""):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE service_providers 
            SET name = ?, server_url = ?, server_key = ?, 
                personalized_key = ?, description = ?
            WHERE id = ?
        """, (name, server_url, server_key, personalized_key, description, provider_id))
        
        if cursor.rowcount == 0:
            raise Exception("未找到指定的提供商")
        
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        if "personalized_key" in str(e):
            raise Exception("个性化密钥已被使用")
        raise
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# 添加获取单个记录的函数
def get_provider_by_id(provider_id: int):
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM service_providers WHERE id = ?", 
        (provider_id,)
    )
    result = cursor.fetchone()
    conn.close()
    return result

def get_model_by_id(model_id: int):
    """获取单个模型信息"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            """SELECT id, provider_id, model_name, description 
               FROM provider_models 
               WHERE id = ?""", 
            (model_id,)
        )
        result = cursor.fetchone()
        return result
    finally:
        conn.close()

def update_provider_model(model_id: int, provider_id: int, model_name: str, description: str = ""):
    """更新提供商模型信息"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        # 检查模型是否存在
        cursor.execute("SELECT id FROM provider_models WHERE id = ?", (model_id,))
        if not cursor.fetchone():
            raise Exception("模型不存在")
        
        # 检查提供商是否存在
        cursor.execute("SELECT id FROM service_providers WHERE id = ?", (provider_id,))
        if not cursor.fetchone():
            raise Exception("提供商不存在")
        
        # 更新模型信息
        cursor.execute(
            """UPDATE provider_models 
               SET provider_id = ?, model_name = ?, description = ?
               WHERE id = ?""",
            (provider_id, model_name, description, model_id)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        raise Exception("该提供商已存在此模型名称")
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

def delete_provider_model(model_id: int):
    """删除提供商模型"""
    conn = sqlite3.connect(str(DATABASE_PATH))
    cursor = conn.cursor()
    try:
        # 检查模型是否存在
        cursor.execute("SELECT id FROM provider_models WHERE id = ?", (model_id,))
        if not cursor.fetchone():
            raise Exception("模型不存在")
        
        # 删除模型
        cursor.execute("DELETE FROM provider_models WHERE id = ?", (model_id,))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        raise
    finally:
        conn.close()

# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ========= Copyright 2023-2024 @ CAMEL-AI.org. All Rights Reserved. =========
# Import from the correct module path
from owl.utils import run_society
import os
import gradio as gr
import time
import json
import logging
import datetime
from typing import Tuple
import importlib
from dotenv import load_dotenv, set_key, find_dotenv, unset_key
import threading
import queue
import re  # For regular expression operations
from owl.common.gradio_messager import gradio_messenger

os.environ["PYTHONIOENCODING"] = "utf-8"


# 配置日志系统
def setup_logging():
    """配置日志系统，将日志输出到文件和内存队列以及控制台"""
    # 创建logs目录（如果不存在）
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")
    os.makedirs(logs_dir, exist_ok=True)

    # 生成日志文件名（使用当前日期）
    current_date = datetime.datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(logs_dir, f"gradio_log_{current_date}.txt")

    # 配置根日志记录器（捕获所有日志）
    root_logger = logging.getLogger()

    # 清除现有的处理器，避免重复日志
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    root_logger.setLevel(logging.INFO)

    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.INFO)

    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # 创建格式化器
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # 添加处理器到根日志记录器
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    logging.info("日志系统已初始化，日志文件: %s", log_file)
    return log_file


# 全局变量
LOG_FILE = None
LOG_QUEUE: queue.Queue = queue.Queue()  # 日志队列
STOP_LOG_THREAD = threading.Event()
CURRENT_PROCESS = None  # 用于跟踪当前运行的进程
STOP_REQUESTED = threading.Event()  # 用于标记是否请求停止













# 日志读取和更新函数
def log_reader_thread(log_file):
    """后台线程，持续读取日志文件并将新行添加到队列中"""
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            # 移动到文件末尾
            f.seek(0, 2)

            while not STOP_LOG_THREAD.is_set():
                line = f.readline()
                if line:
                    LOG_QUEUE.put(line)  # 添加到对话记录队列
                else:
                    # 没有新行，等待一小段时间
                    time.sleep(0.1)
    except Exception as e:
        logging.error(f"日志读取线程出错: {str(e)}")



# 修改get_latest_logs函数以使用GradioMessenger
def get_latest_logs(max_lines=100, queue_source=None):
    """从队列中获取最新的日志行
    
    Args:
        max_lines: 最大返回行数
        queue_source: 指定使用哪个队列，默认为LOG_QUEUE (不再使用)

    Returns:
        str: 日志内容
    """
    # 获取GradioMessenger中的格式化聊天历史
    chat_history = gradio_messenger.get_formatted_chat_history(max_lines, content_type="text")
    if chat_history and chat_history != "暂无对话记录。":
        return chat_history
    
    # 如果GradioMessenger中没有消息，返回提示信息
    return "暂无对话记录。"


# 修改get_latest_images函数以确保图片正确显示
def get_latest_images(max_images=20):
    """获取最新的图片内容
    
    Args:
        max_images: 最大返回图片数
        
    Returns:
        list: 图片路径列表
    """
    images = gradio_messenger.get_formatted_chat_history(max_images, content_type="image")
    
    # 确保所有图片路径都是有效的
    valid_images = []
    for img in images:
        if isinstance(img, str):
            # 检查是否为有效的图片URL或路径
            if img.startswith("http"):
                valid_images.append(img)
                # logging.info(f"有效图片URL: {img}")
            elif os.path.exists(img) and any(img.lower().endswith(ext) for ext in 
                                           ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                # 确保是绝对路径
                if not os.path.isabs(img):
                    img = os.path.abspath(img)
                valid_images.append(img)
                # logging.info(f"有效本地图片: {img}")
            else:
                logging.warning(f"无效图片路径: {img}")
        else:
            # 非字符串类型的图片内容
            valid_images.append(img)
            logging.info("添加非字符串类型图片内容")
    
    # logging.info(f"最终返回 {len(valid_images)} 张有效图片")
    return valid_images


# 新增函数获取HTML内容
def get_latest_html(max_items=20):
    """获取最新的HTML内容
    
    Args:
        max_items: 最大返回HTML项目数
        
    Returns:
        str: HTML内容
    """
    html_content = gradio_messenger.get_formatted_chat_history(1, content_type="html")
    if not html_content or html_content == "<div class='no-content'>暂无HTML内容</div>":
        return "<div class='no-content'>暂无HTML内容</div>"
    
    # 修复HTML中的相对图片路径
    base_dir = "/Users/wangyaqi49/code_room/github/owl"
    
    # 使用正则表达式查找所有img标签的src属性
    def replace_img_src(match):
        src = match.group(1)
        # 只处理相对路径（不以http、https开头的路径）
        if not (src.startswith('http://') or src.startswith('https://')):
            try:
                # 只获取文件名部分
                img_filename = os.path.basename(src)
                # 拼接到目录前缀
                full_path = os.path.join(base_dir, img_filename)
                
                # 检查文件是否存在
                if os.path.exists(full_path):
                    # 读取图片文件并转换为base64
                    import base64
                    import mimetypes
                    
                    # 获取MIME类型
                    mime_type, _ = mimetypes.guess_type(full_path)
                    if not mime_type:
                        mime_type = 'image/png'  # 默认MIME类型
                    
                    with open(full_path, "rb") as img_file:
                        img_data = base64.b64encode(img_file.read()).decode('utf-8')
                    
                    # 返回data URI
                    return f'src="data:{mime_type};base64,{img_data}"'
                else:
                    logging.warning(f"图片文件不存在: {full_path}")
            except Exception as e:
                logging.warning(f"处理图片时出错: {src}, 错误: {e}")
                
        return f'src="{src}"'
    
    # 替换所有img标签的src属性
    html_content = re.sub(r'src="([^"]+)"', replace_img_src, html_content)
    
    # 添加基本样式以确保HTML内容正确显示
    styled_html = f"""
    <style>
        .html-content-container {{
            background-color: white;
            border-radius: 8px;
            padding: 15px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
            overflow: auto;
            max-height: 100%;
        }}
        .html-content-container img {{
            max-width: 100%;
            height: auto;
        }}
    </style>
    <div class="html-content-container">
        {html_content}
    </div>
    """
    
    return styled_html


# Dictionary containing module descriptions
MODULE_DESCRIPTIONS = {
    "run": "默认模式：使用OpenAI模型的默认的智能体协作模式，适合大多数任务。",
    "run_mini": "使用使用OpenAI模型最小化配置处理任务",
    "run_deepseek_zh": "使用deepseek模型处理中文任务",
    "run_openai_compatiable_model": "使用openai兼容模型处理任务",
    "run_ollama": "使用本地ollama模型处理任务",
    "run_qwen_mini_zh": "使用qwen模型最小化配置处理任务",
    "run_qwen_zh": "使用qwen模型处理任务",
    "run_ori": "使用混合模型和自定义浏览器工具包处理任务，支持图文并茂的HTML报告生成",
}


# 默认环境变量模板
DEFAULT_ENV_TEMPLATE = """#===========================================
# MODEL & API 
# (See https://docs.camel-ai.org/key_modules/models.html#)
#===========================================

# OPENAI API (https://platform.openai.com/api-keys)
OPENAI_API_KEY='Your_Key'
# OPENAI_API_BASE_URL=""

# Azure OpenAI API
# AZURE_OPENAI_BASE_URL=""
# AZURE_API_VERSION=""
# AZURE_OPENAI_API_KEY=""
# AZURE_DEPLOYMENT_NAME=""


# Qwen API (https://help.aliyun.com/zh/model-studio/developer-reference/get-api-key)
QWEN_API_KEY='Your_Key'

# DeepSeek API (https://platform.deepseek.com/api_keys)
DEEPSEEK_API_KEY='Your_Key'

#===========================================
# Tools & Services API
#===========================================

# Google Search API (https://coda.io/@jon-dallas/google-image-search-pack-example/search-engine-id-and-google-api-key-3)
GOOGLE_API_KEY='Your_Key'
SEARCH_ENGINE_ID='Your_ID'

# Chunkr API (https://chunkr.ai/)
CHUNKR_API_KEY='Your_Key'

# Firecrawl API (https://www.firecrawl.dev/)
FIRECRAWL_API_KEY='Your_Key'
#FIRECRAWL_API_URL="https://api.firecrawl.dev"
"""


def validate_input(question: str) -> bool:
    """验证用户输入是否有效

    Args:
        question: 用户问题

    Returns:
        bool: 输入是否有效
    """
    # 检查输入是否为空或只包含空格
    if not question or question.strip() == "":
        return False
    return True


# 修改run_society函数以确保它使用我们的日志系统
def patched_run_society(society, *args, **kwargs):
    """包装run_society函数，确保它使用我们的消息传递系统"""
    # logging.info("开始运行社会模拟...")
    # gradio_messenger.send_message("system", "开始运行社会模拟...", content_type="text", add_to_log=True)
    
    try:
        # 调用原始函数
        result = run_society(society, *args, **kwargs)
        
        # logging.info("社会模拟运行完成")
        # gradio_messenger.send_message("system", "社会模拟运行完成", content_type="text", add_to_log=True)
        
        # 如果结果包含聊天历史，将其添加到GradioMessenger
        if isinstance(result, tuple) and len(result) >= 2:
            answer, chat_history = result[0], result[1]
            
            # 将聊天历史添加到GradioMessenger
            if chat_history and isinstance(chat_history, list):
                for message in chat_history:
                    if isinstance(message, dict) and "role" in message and "content" in message:
                        # 检测内容类型
                        content = message["content"]
                        content_type = "text"  # 默认为文本
                        
                        # 检查是否为图片路径或URL
                        if isinstance(content, str):
                            # 图片URL检测
                            if content.startswith("http") and any(ext in content.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                content_type = "image"
                                # logging.info(f"检测到图片URL: {content}")
                            # 本地图片路径检测
                            elif os.path.exists(content) and any(content.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                                content_type = "image"
                                # 确保是绝对路径
                                if not os.path.isabs(content):
                                    content = os.path.abspath(content)
                                # logging.info(f"检测到本地图片: {content}")
                            # HTML内容检测 - 更宽松的检测条件
                            elif (("<html" in content.lower() or "<body" in content.lower() or 
                                  "<div" in content.lower() or "<table" in content.lower() or 
                                  "<p" in content.lower() or "<h1" in content.lower() or
                                  "<h2" in content.lower() or "<h3" in content.lower() or
                                  "<ul" in content.lower() or "<ol" in content.lower() or
                                  "<li" in content.lower() or "<span" in content.lower() or
                                  "<style" in content.lower() or "<script" in content.lower() or
                                  "<a href" in content.lower() or "<img" in content.lower()) and
                                  len(content) > 50):  # 确保内容足够长，避免误判
                                content_type = "html"
                                # logging.info(f"检测到HTML内容，长度={len(content)}")
                        
                        # 发送消息到对应类型的队列
                        gradio_messenger.send_message(
                            message["role"], 
                            content, 
                            content_type=content_type,
                            add_to_log=True  # 记录到日志以便调试
                        )
                        # logging.info(f"已添加{content_type}类型消息到队列")
            
            # 检测并处理最终答案的内容类型
            if answer:
                content_type = "text"  # 默认为文本
                if isinstance(answer, str):
                    # 图片URL检测
                    if answer.startswith("http") and any(ext in answer.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        content_type = "image"
                        # logging.info(f"最终答案是图片URL: {answer}")
                    # 本地图片路径检测
                    elif os.path.exists(answer) and any(answer.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        content_type = "image"
                        # 确保是绝对路径
                        if not os.path.isabs(answer):
                            answer = os.path.abspath(answer)
                        # logging.info(f"最终答案是本地图片: {answer}")
                    # HTML内容检测
                    elif ("<html" in answer.lower() or "<div" in answer.lower() or 
                          "<table" in answer.lower() or "<p" in answer.lower()):
                        content_type = "html"
                        # logging.info("最终答案是HTML内容")
                
                # 发送最终答案到对应类型的队列
                gradio_messenger.send_message(
                    "assistant", 
                    answer, 
                    content_type=content_type,
                    add_to_log=True
                )
                # logging.info(f"已添加最终答案({content_type}类型)到队列")
        
        return result
    except Exception as e:
        error_msg = f"社会模拟运行出错: {str(e)}"
        logging.error(error_msg)
        gradio_messenger.send_message("system", error_msg, content_type="text", add_to_log=True)
        raise


def run_owl(question: str, example_module: str) -> Tuple[str, str, str]:
    """运行OWL系统并返回结果

    Args:
        question: 用户问题
        example_module: 要导入的示例模块名（如 "run_terminal_zh" 或 "run_deep"）

    Returns:
        Tuple[...]: 回答、令牌计数、状态
    """
    global CURRENT_PROCESS

    # 验证输入
    if not validate_input(question):
        logging.warning("用户提交了无效的输入")
        return ("请输入有效的问题", "0", "❌ 错误: 输入问题无效")

    try:
        # 确保环境变量已加载
        load_dotenv(find_dotenv(), override=True)
        logging.info(f"处理问题: '{question}', 使用模块: {example_module}")

        # 检查模块是否在MODULE_DESCRIPTIONS中
        if example_module not in MODULE_DESCRIPTIONS:
            logging.error(f"用户选择了不支持的模块: {example_module}")
            return (
                f"所选模块 '{example_module}' 不受支持",
                "0",
                "❌ 错误: 不支持的模块",
            )

        # 动态导入目标模块
        module_path = f"examples.{example_module}"
        try:
            logging.info(f"正在导入模块: {module_path}")
            module = importlib.import_module(module_path)
        except ImportError as ie:
            logging.error(f"无法导入模块 {module_path}: {str(ie)}")
            return (
                f"无法导入模块: {module_path}",
                "0",
                f"❌ 错误: 模块 {example_module} 不存在或无法加载 - {str(ie)}",
            )
        except Exception as e:
            logging.error(f"导入模块 {module_path} 时发生错误: {str(e)}")
            return (f"导入模块时发生错误: {module_path}", "0", f"❌ 错误: {str(e)}")

        # 检查是否包含construct_society函数
        if not hasattr(module, "construct_society"):
            logging.error(f"模块 {module_path} 中未找到 construct_society 函数")
            return (
                f"模块 {module_path} 中未找到 construct_society 函数",
                "0",
                "❌ 错误: 模块接口不兼容",
            )

        # 构建社会模拟
        try:
            logging.info("正在构建社会模拟...")
            
            # 特殊处理run_ori模块，应用prompt patch
            if example_module == "run_ori":
                from unittest.mock import patch
                from camel.prompts.ai_society import AISocietyPromptTemplateDict
                
                # 导入run_ori中定义的新prompt
                new_ASSISTANT_PROMPT = module.new_ASSISTANT_PROMPT
                new_USER_PROMPT = module.new_USER_PROMPT
                
                # 使用patch应用新prompt
                with patch.multiple(AISocietyPromptTemplateDict, 
                                   ASSISTANT_PROMPT=new_ASSISTANT_PROMPT,
                                   USER_PROMPT=new_USER_PROMPT):
                    society = module.construct_society(question)
                    
                    # 运行社会模拟 - 使用我们的包装函数
                    logging.info("正在运行社会模拟...")
                    
                    # 添加更多详细日志以便调试
                    logging.info(f"社会模拟配置: {society.__dict__}")
                    
                    answer, chat_history, token_info = patched_run_society(society)
                    logging.info(f"社会模拟运行完成，获得回答长度: {len(answer) if answer else 0}")
            else:
                # 常规模块处理
                society = module.construct_society(question)
                
                # 运行社会模拟 - 使用我们的包装函数
                logging.info("正在运行社会模拟...")
                
                # 添加更多详细日志以便调试
                logging.info(f"社会模拟配置: {society.__dict__}")
                
                answer, chat_history, token_info = patched_run_society(society)
                logging.info(f"社会模拟运行完成，获得回答长度: {len(answer) if answer else 0}")

            # 记录对话历史以便在Gradio界面显示
            if chat_history:
                logging.info(f"对话历史记录: {chat_history}")
                
                # 尝试以更结构化的方式记录对话历史
                for i, message in enumerate(chat_history):
                    if isinstance(message, dict):
                        role = message.get('role', 'unknown')
                        content = message.get('content', '')
                        logging.info(f"消息 {i}, 角色: {role}, 内容: {content}")

        except Exception as e:
            logging.error(f"构建或运行社会模拟时发生错误: {str(e)}")
            return (
                f"构建或运行社会模拟时发生错误: {str(e)}",
                "0",
                f"❌ 错误: {str(e)}",
            )

        # 安全地获取令牌计数
        if not isinstance(token_info, dict):
            token_info = {}

        completion_tokens = token_info.get("completion_token_count", 0)
        prompt_tokens = token_info.get("prompt_token_count", 0)
        total_tokens = completion_tokens + prompt_tokens

        logging.info(
            f"处理完成，令牌使用: 完成={completion_tokens}, 提示={prompt_tokens}, 总计={total_tokens}"
        )

        return (
            answer,
            f"完成令牌: {completion_tokens:,} | 提示令牌: {prompt_tokens:,} | 总计: {total_tokens:,}",
            "✅ 成功完成",
        )

    except Exception as e:
        logging.error(f"处理问题时发生未捕获的错误: {str(e)}")
        return (f"发生错误: {str(e)}", "0", f"❌ 错误: {str(e)}")


def update_module_description(module_name: str) -> str:
    """返回所选模块的描述"""
    return MODULE_DESCRIPTIONS.get(module_name, "无可用描述")


# 存储前端配置的环境变量
WEB_FRONTEND_ENV_VARS: dict[str, str] = {}


def init_env_file():
    """初始化.env文件如果不存在"""
    dotenv_path = find_dotenv()
    if not dotenv_path:
        with open(".env", "w") as f:
            f.write(DEFAULT_ENV_TEMPLATE)
        dotenv_path = find_dotenv()
    return dotenv_path


def load_env_vars():
    """加载环境变量并返回字典格式

    Returns:
        dict: 环境变量字典，每个值为一个包含值和来源的元组 (value, source)
    """
    dotenv_path = init_env_file()
    load_dotenv(dotenv_path, override=True)

    # 从.env文件读取环境变量
    env_file_vars = {}
    with open(dotenv_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_file_vars[key.strip()] = value.strip().strip("\"'")

    # 从系统环境变量中获取
    system_env_vars = {
        k: v
        for k, v in os.environ.items()
        if k not in env_file_vars and k not in WEB_FRONTEND_ENV_VARS
    }

    # 合并环境变量，并标记来源
    env_vars = {}

    # 添加系统环境变量（最低优先级）
    for key, value in system_env_vars.items():
        env_vars[key] = (value, "系统")

    # 添加.env文件环境变量（中等优先级）
    for key, value in env_file_vars.items():
        env_vars[key] = (value, ".env文件")

    # 添加前端配置的环境变量（最高优先级）
    for key, value in WEB_FRONTEND_ENV_VARS.items():
        env_vars[key] = (value, "前端配置")
        # 确保操作系统环境变量也被更新
        os.environ[key] = value

    return env_vars


def save_env_vars(env_vars):
    """保存环境变量到.env文件

    Args:
        env_vars: 字典，键为环境变量名，值可以是字符串或(值,来源)元组
    """
    try:
        dotenv_path = init_env_file()

        # 保存每个环境变量
        for key, value_data in env_vars.items():
            if key and key.strip():  # 确保键不为空
                # 处理值可能是元组的情况
                if isinstance(value_data, tuple):
                    value = value_data[0]
                else:
                    value = value_data

                set_key(dotenv_path, key.strip(), value.strip())

        # 重新加载环境变量以确保生效
        load_dotenv(dotenv_path, override=True)

        return True, "环境变量已成功保存！"
    except Exception as e:
        return False, f"保存环境变量时出错: {str(e)}"


def add_env_var(key, value, from_frontend=True):
    """添加或更新单个环境变量

    Args:
        key: 环境变量名
        value: 环境变量值
        from_frontend: 是否来自前端配置，默认为True
    """
    try:
        if not key or not key.strip():
            return False, "变量名不能为空"

        key = key.strip()
        value = value.strip()

        # 如果来自前端，则添加到前端环境变量字典
        if from_frontend:
            WEB_FRONTEND_ENV_VARS[key] = value
            # 直接更新系统环境变量
            os.environ[key] = value

        # 同时更新.env文件
        dotenv_path = init_env_file()
        set_key(dotenv_path, key, value)
        load_dotenv(dotenv_path, override=True)

        return True, f"环境变量 {key} 已成功添加/更新！"
    except Exception as e:
        return False, f"添加环境变量时出错: {str(e)}"


def delete_env_var(key):
    """删除环境变量"""
    try:
        if not key or not key.strip():
            return False, "变量名不能为空"

        key = key.strip()

        # 从.env文件中删除
        dotenv_path = init_env_file()
        unset_key(dotenv_path, key)

        # 从前端环境变量字典中删除
        if key in WEB_FRONTEND_ENV_VARS:
            del WEB_FRONTEND_ENV_VARS[key]

        # 从当前进程环境中也删除
        if key in os.environ:
            del os.environ[key]

        return True, f"环境变量 {key} 已成功删除！"
    except Exception as e:
        return False, f"删除环境变量时出错: {str(e)}"


def is_api_related(key: str) -> bool:
    """判断环境变量是否与API相关

    Args:
        key: 环境变量名

    Returns:
        bool: 是否与API相关
    """
    # API相关的关键词
    api_keywords = [
        "api",
        "key",
        "token",
        "secret",
        "password",
        "openai",
        "qwen",
        "deepseek",
        "google",
        "search",
        "hf",
        "hugging",
        "chunkr",
        "firecrawl",
    ]

    # 检查是否包含API相关关键词（不区分大小写）
    return any(keyword in key.lower() for keyword in api_keywords)


def get_api_guide(key: str) -> str:
    """根据环境变量名返回对应的API获取指南

    Args:
        key: 环境变量名

    Returns:
        str: API获取指南链接或说明
    """
    key_lower = key.lower()
    if "openai" in key_lower:
        return "https://platform.openai.com/api-keys"
    elif "qwen" in key_lower or "dashscope" in key_lower:
        return "https://help.aliyun.com/zh/model-studio/developer-reference/get-api-key"
    elif "deepseek" in key_lower:
        return "https://platform.deepseek.com/api_keys"
    elif "google" in key_lower:
        return "https://coda.io/@jon-dallas/google-image-search-pack-example/search-engine-id-and-google-api-key-3"
    elif "search_engine_id" in key_lower:
        return "https://coda.io/@jon-dallas/google-image-search-pack-example/search-engine-id-and-google-api-key-3"
    elif "chunkr" in key_lower:
        return "https://chunkr.ai/"
    elif "firecrawl" in key_lower:
        return "https://www.firecrawl.dev/"
    else:
        return ""


def update_env_table():
    """更新环境变量表格显示，只显示API相关的环境变量"""
    env_vars = load_env_vars()
    # 过滤出API相关的环境变量
    api_env_vars = {k: v for k, v in env_vars.items() if is_api_related(k)}
    # 转换为列表格式，以符合Gradio Dataframe的要求
    # 格式: [变量名, 变量值, 获取指南链接]
    result = []
    for k, v in api_env_vars.items():
        guide = get_api_guide(k)
        # 如果有指南链接，创建一个可点击的链接
        guide_link = (
            f"<a href='{guide}' target='_blank' class='guide-link'>🔗 获取</a>"
            if guide
            else ""
        )
        result.append([k, v[0], guide_link])
    return result


def save_env_table_changes(data):
    """保存环境变量表格的更改

    Args:
        data: Dataframe数据，可能是pandas DataFrame对象

    Returns:
        str: 操作状态信息，包含HTML格式的状态消息
    """
    try:
        logging.info(f"开始处理环境变量表格数据，类型: {type(data)}")

        # 获取当前所有环境变量
        current_env_vars = load_env_vars()
        processed_keys = set()  # 记录已处理的键，用于检测删除的变量

        # 处理pandas DataFrame对象
        import pandas as pd

        if isinstance(data, pd.DataFrame):
            # 获取列名信息
            columns = data.columns.tolist()
            logging.info(f"DataFrame列名: {columns}")

            # 遍历DataFrame的每一行
            for index, row in data.iterrows():
                # 使用列名访问数据
                if len(columns) >= 3:
                    # 获取变量名和值 (第0列是变量名，第1列是值)
                    key = row[0] if isinstance(row, pd.Series) else row.iloc[0]
                    value = row[1] if isinstance(row, pd.Series) else row.iloc[1]

                    # 检查是否为空行或已删除的变量
                    if key and str(key).strip():  # 如果键名不为空，则添加或更新
                        logging.info(f"处理环境变量: {key} = {value}")
                        add_env_var(key, str(value))
                        processed_keys.add(key)
        # 处理其他格式
        elif isinstance(data, dict):
            logging.info(f"字典格式数据的键: {list(data.keys())}")
            # 如果是字典格式，尝试不同的键
            if "data" in data:
                rows = data["data"]
            elif "values" in data:
                rows = data["values"]
            elif "value" in data:
                rows = data["value"]
            else:
                # 尝试直接使用字典作为行数据
                rows = []
                for key, value in data.items():
                    if key not in ["headers", "types", "columns"]:
                        rows.append([key, value])

            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, list) and len(row) >= 2:
                        key, value = row[0], row[1]
                        if key and str(key).strip():
                            add_env_var(key, str(value))
                            processed_keys.add(key)
        elif isinstance(data, list):
            # 列表格式
            for row in data:
                if isinstance(row, list) and len(row) >= 2:
                    key, value = row[0], row[1]
                    if key and str(key).strip():
                        add_env_var(key, str(value))
                        processed_keys.add(key)
        else:
            logging.error(f"未知的数据格式: {type(data)}")
            return f"❌ 保存失败: 未知的数据格式 {type(data)}"

        # 处理删除的变量 - 检查当前环境变量中是否有未在表格中出现的变量
        api_related_keys = {k for k in current_env_vars.keys() if is_api_related(k)}
        keys_to_delete = api_related_keys - processed_keys

        # 删除不再表格中的变量
        for key in keys_to_delete:
            logging.info(f"删除环境变量: {key}")
            delete_env_var(key)

        return "✅ 环境变量已成功保存"
    except Exception as e:
        import traceback

        error_details = traceback.format_exc()
        logging.error(f"保存环境变量时出错: {str(e)}\n{error_details}")
        return f"❌ 保存失败: {str(e)}"


def get_env_var_value(key):
    """获取环境变量的实际值

    优先级：前端配置 > .env文件 > 系统环境变量
    """
    # 检查前端配置的环境变量
    if key in WEB_FRONTEND_ENV_VARS:
        return WEB_FRONTEND_ENV_VARS[key]

    # 检查系统环境变量（包括从.env加载的）
    return os.environ.get(key, "")


def create_ui():
    """创建简化版Gradio界面"""

    def clear_log_file():
        """清空日志文件内容和消息队列"""
        try:
            if LOG_FILE and os.path.exists(LOG_FILE):
                # 清空日志文件内容而不是删除文件
                open(LOG_FILE, "w").close()
                logging.info("日志文件已清空")
                # 清空日志队列
                while not LOG_QUEUE.empty():
                    try:
                        LOG_QUEUE.get_nowait()
                    except queue.Empty:
                        break
                # 清空GradioMessenger消息
                gradio_messenger.clear_messages()
                return "", [], ""  # 返回三种内容类型的空值
            else:
                return "", [], ""
        except Exception as e:
            logging.error(f"清空日志文件时出错: {str(e)}")
            return "", [], ""

    # 修改process_with_live_logs函数以确保内容正确刷新
    def process_with_live_logs(question):
        """处理问题并实时更新日志"""
        global CURRENT_PROCESS

        # 清空日志文件和消息队列
        clear_log_file()
        
        # 添加用户问题到GradioMessenger
        gradio_messenger.send_message("user", question, content_type="text")

        # 创建一个后台线程来处理问题
        result_queue = queue.Queue()

        def process_in_background():
            try:
                # 使用固定的模块 "run_ori"
                result = run_owl(question, "run_ori")
                result_queue.put(result)
            except Exception as e:
                error_msg = f"发生错误: {str(e)}"
                gradio_messenger.send_message("system", error_msg, content_type="text")
                result_queue.put((error_msg, "0", f"❌ 错误: {str(e)}"))

        # 启动后台处理线程
        bg_thread = threading.Thread(target=process_in_background)
        CURRENT_PROCESS = bg_thread  # 记录当前进程
        bg_thread.start()

        # 在等待处理完成的同时，每秒更新一次日志
        while bg_thread.is_alive():
            # 更新各种内容显示
            text_logs = get_latest_logs(100, LOG_QUEUE)
            
            # 获取并记录图片更新情况
            image_logs = get_latest_images(20)
            
            # 获取HTML内容
            html_logs = get_latest_html(20)
            
            # 始终更新状态和所有内容类型
            yield (
                "0",
                "<span class='status-indicator status-running'></span> 处理中...",
                text_logs,
                image_logs,
                html_logs
            )

            time.sleep(1)  # 每秒更新一次

        # 处理完成，获取结果
        if not result_queue.empty():
            result = result_queue.get()
            answer, token_count, status = result
            
            # 如果有回答，添加到GradioMessenger
            if answer and "错误" not in status:
                # 检测回答类型
                content_type = "text"
                if isinstance(answer, str):
                    # 图片URL检测
                    if answer.startswith("http") and any(ext in answer.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        content_type = "image"
                    # 本地图片路径检测
                    elif os.path.exists(answer) and any(answer.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
                        content_type = "image"
                        # 确保是绝对路径
                        if not os.path.isabs(answer):
                            answer = os.path.abspath(answer)
                    # HTML内容检测
                    elif ("<html" in answer.lower() or "<div" in answer.lower() or 
                          "<table" in answer.lower() or "<p" in answer.lower()):
                        content_type = "html"
                
                # 发送最终答案到对应类型的队列
                gradio_messenger.send_message("assistant", answer, content_type=content_type)
                logging.info(f"已添加最终答案({content_type}类型)到队列")

            # 最后一次更新所有内容
            text_logs = get_latest_logs(100, LOG_QUEUE)
            
            # 获取并记录最终图片
            image_logs = get_latest_images(20)
            logging.info(f"最终图片显示，获取到 {len(image_logs)} 张图片: {image_logs}")
            
            # 获取最终HTML内容
            html_logs = get_latest_html(20)

            # 根据状态设置不同的指示器
            if "错误" in status:
                status_with_indicator = (
                    f"<span class='status-indicator status-error'></span> {status}"
                )
            else:
                status_with_indicator = (
                    f"<span class='status-indicator status-success'></span> {status}"
                )

            yield token_count, status_with_indicator, text_logs, image_logs, html_logs
        else:
            text_logs = get_latest_logs(100, LOG_QUEUE)
            image_logs = get_latest_images(20)
            html_logs = get_latest_html(20)
            yield (
                "0",
                "<span class='status-indicator status-error'></span> 已终止",
                text_logs,
                image_logs,
                html_logs
            )

    with gr.Blocks(theme=gr.themes.Soft(primary_hue="blue")) as app:
        # 添加自定义CSS
        gr.HTML("""
            <style>
            /* 聊天容器样式 */
            .chat-container .chatbot {
                height: 500px;
                overflow-y: auto;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
            }
            
            /* 内容显示区域样式 */
            .content-display {
                height: 600px !important; /* 增加高度从400px到600px */
                max-height: 800px !important; /* 增加最大高度限制 */
                overflow-y: auto !important;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);
                margin-bottom: 10px;
                resize: vertical; /* 添加垂直方向可调整大小功能 */
            }
            
            /* 文本内容区域 */
            .text-display textarea {
                height: 600px !important; /* 增加高度从400px到600px */
                max-height: 800px !important; /* 增加最大高度限制 */
                overflow-y: auto !important;
                font-family: monospace;
                font-size: 0.9em;
                white-space: pre-wrap;
                line-height: 1.4;
                resize: vertical; /* 添加垂直方向可调整大小功能 */
            }
            
            /* 图片内容区域 */
            .image-display {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                padding: 10px;
                background-color: #f9f9f9;
                border-radius: 10px;
                resize: vertical; /* 添加垂直方向可调整大小功能 */
            }
            
            .image-display img {
                max-width: 100%;
                max-height: 300px;
                object-fit: contain;
                border-radius: 5px;
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
            }
            
            /* HTML内容区域 */
            .html-display {
                padding: 10px;
                background-color: white;
                border-radius: 10px;
                box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                resize: vertical; /* 添加垂直方向可调整大小功能 */
            }
            
            /* 添加调整大小指示器 */
            .resizable-notice {
                font-size: 0.8em;
                color: #888;
                text-align: right;
                margin-top: -5px;
                margin-bottom: 5px;
            }
            
            /* 其余样式保持不变 */
            .no-content {
                color: #888;
                font-style: italic;
                text-align: center;
                padding: 20px;
            }

            /* 改进标签页样式 */
            .tabs .tab-nav {
                background-color: #f5f5f5;
                border-radius: 8px 8px 0 0;
                padding: 5px;
            }
            
            .tabs .tab-nav button {
                border-radius: 5px;
                margin: 0 3px;
                padding: 8px 15px;
                font-weight: 500;
            }
            
            .tabs .tab-nav button.selected {
                background-color: #2c7be5;
                color: white;
            }
            
            /* 状态指示器样式 */
            .status-indicator {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                margin-right: 5px;
            }
            
            .status-running {
                background-color: #ffc107;
                animation: pulse 1.5s infinite;
            }
            
            .status-success {
                background-color: #28a745;
            }
            
            .status-error {
                background-color: #dc3545;
            }
            
            /* 环境变量管理样式 */
            .env-manager-container {
                border-radius: 10px;
                padding: 15px;
                background-color: #f9f9f9;
                margin-bottom: 20px;
            }
            
            .env-controls, .api-help-container {
                border-radius: 8px;
                padding: 15px;
                background-color: white;
                box-shadow: 0 2px 6px rgba(0, 0, 0, 0.05);
                height: 100%;
            }
            
            .env-add-group, .env-delete-group {
                margin-top: 20px;
                padding: 15px;
                border-radius: 8px;
                background-color: #f5f8ff;
                border: 1px solid #e0e8ff;
            }
            
            .env-delete-group {
                background-color: #fff5f5;
                border: 1px solid #ffe0e0;
            }
            
            .env-buttons {
                justify-content: flex-start;
                gap: 10px;
                margin-top: 10px;
            }
            
            .env-button {
                min-width: 100px;
            }
            
            .delete-button {
                background-color: #dc3545;
                color: white;
            }
            
            .env-table {
                margin-bottom: 15px;
            }
            
            /* 改进环境变量表格样式 */
            .env-table table {
                border-collapse: separate;
                border-spacing: 0;
                width: 100%;
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            
            .env-table th {
                background-color: #f0f7ff;
                padding: 12px 15px;
                text-align: left;
                font-weight: 600;
                color: #2c7be5;
                border-bottom: 2px solid #e0e8ff;
            }
            
            .env-table td {
                padding: 10px 15px;
                border-bottom: 1px solid #f0f0f0;
            }
            
            .env-table tr:hover td {
                background-color: #f9fbff;
            }
            
            .env-table tr:last-child td {
                border-bottom: none;
            }
            
            /* 状态图标样式 */
            .status-icon-cell {
                text-align: center;
                font-size: 1.2em;
            }
            
            /* 链接样式 */
            .guide-link {
                color: #2c7be5;
                text-decoration: none;
                cursor: pointer;
                font-weight: 500;
            }
            
            .guide-link:hover {
                text-decoration: underline;
            }
            
            .env-status {
                margin-top: 15px;
                font-weight: 500;
                padding: 10px;
                border-radius: 6px;
                transition: all 0.3s ease;
            }
            
            .env-status-success {
                background-color: #d4edda;
                color: #155724;
                border: 1px solid #c3e6cb;
            }
            
            .env-status-error {
                background-color: #f8d7da;
                color: #721c24;
                border: 1px solid #f5c6cb;
            }
            
            .api-help-accordion {
                margin-bottom: 8px;
                border-radius: 6px;
                overflow: hidden;
            }
            
            /* 新增布局样式 */
            .main-input-container {
                margin-bottom: 20px;
                padding: 15px;
                background-color: #f9f9f9;
                border-radius: 10px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            
            .content-panels {
                display: flex;
                flex-direction: column;
                gap: 20px;
            }
            
            .panel-header {
                font-weight: 600;
                color: #2c7be5;
                margin-bottom: 10px;
                padding-bottom: 5px;
                border-bottom: 2px solid #e0e8ff;
            }
            
            .panel-container {
                background-color: white;
                border-radius: 10px;
                padding: 15px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }
            
            .top-panels {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
            }
            
            .top-panel {
                flex: 1;
                min-height: 600px; /* 增加最小高度从400px到600px */
            }
            
            .bottom-panel {
                min-height: 400px; /* 增加最小高度从300px到400px */
            }

            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.5; }
                100% { opacity: 1; }
            }
            </style>
            """)

        # 顶部输入区域 - 简化版
        with gr.Box(elem_classes="main-input-container"):
            # 先定义输入框
            with gr.Row():
                with gr.Column(scale=3):
                    question_input = gr.Textbox(
                        lines=3,
                        placeholder="请输入您的问题...",
                        label="问题",
                        elem_id="question_input",
                        show_copy_button=True,
                        value="请给出周星驰三个不同时期特点的分析报告",
                    )
                
                with gr.Column(scale=1):
                    # 移除模块选择和描述，只保留按钮和状态
                    with gr.Row():
                        run_button = gr.Button(
                            "运行", variant="primary", elem_classes="primary"
                        )
                        clear_content_button = gr.Button("清空所有内容", variant="secondary")

                    status_output = gr.HTML(
                        value="<span class='status-indicator status-success'></span> 已就绪",
                        label="状态",
                    )
                    token_count_output = gr.Textbox(
                        label="令牌计数", interactive=False, elem_classes="token-count"
                    )
            
            # 然后定义示例，放在输入框下方
            examples = [
                "整理重庆最好玩的两个景点",
                "分析当前NBA最强的三个球员,生成一份对比",
                "请给出周星驰三个不同时期的照片,并总结当时的人物特点"
            ]
            gr.Examples(examples=examples, inputs=question_input)
        # 内容显示区域 - 使用分离的面板而不是标签页
        with gr.Box(elem_classes="content-panels"):
            # 上方两个面板并排
            with gr.Row(elem_classes="top-panels"):
                # 左侧面板 - 思考过程
                with gr.Column(elem_classes="top-panel"):
                    gr.HTML("<div class='panel-header'>思考过程</div>")
                    # gr.HTML("<div class='resizable-notice'>↕️ 可拖动底部边缘调整大小</div>") # 添加调整大小提示
                    with gr.Box(elem_classes="panel-container"):
                        # 文本内容显示区域
                        text_display = gr.Textbox(
                            lines=30, # 增加行数从20到30
                            max_lines=150, # 增加最大行数从100到150
                            interactive=False,
                            autoscroll=True,
                            show_copy_button=True,
                            elem_classes="text-display content-display",
                            container=True,
                            value="",
                        )

                        with gr.Row():
                            refresh_text_button = gr.Button("刷新")
                            auto_refresh_text = gr.Checkbox(
                                label="自动刷新", value=True, interactive=True
                            )

                # 右侧面板 - 界面历史
                with gr.Column(elem_classes="top-panel"):
                    gr.HTML("<div class='panel-header'>界面历史</div>")
                    gr.HTML("<div class='resizable-notice'>↕️ 可拖动底部边缘调整大小</div>") # 添加调整大小提示
                    with gr.Box(elem_classes="panel-container"):
                        # 图片内容显示区域
                        image_display = gr.Gallery(
                            show_label=False,
                            elem_classes="image-display content-display",
                            columns=2,
                            rows=3, # 增加行数从2到3
                            height=550, # 增加高度从350到550
                            object_fit="contain"
                        )
                        
                        with gr.Row():
                            refresh_image_button = gr.Button("刷新")
                            auto_refresh_image = gr.Checkbox(
                                label="自动刷新", value=True, interactive=True
                            )

            # 下方面板 - 实时报告结果
            with gr.Box(elem_classes="bottom-panel"):
                gr.HTML("<div class='panel-header'>实时报告结果</div>")
                gr.HTML("<div class='resizable-notice'>↕️ 可拖动底部边缘调整大小</div>") # 添加调整大小提示
                with gr.Box(elem_classes="panel-container"):
                    # HTML内容显示区域
                    html_display = gr.HTML(
                        value="<div class='no-content'>暂无HTML内容</div>",
                        elem_classes="html-display content-display"
                    )
                    
                    with gr.Row():
                        refresh_html_button = gr.Button("刷新")
                        auto_refresh_html = gr.Checkbox(
                            label="自动刷新", value=True, interactive=True
                        )

            # 环境变量管理标签页保留在原来的位置，但作为单独的标签页
            with gr.Accordion("环境变量管理", open=False):
                with gr.Box(elem_classes="env-manager-container"):
                    gr.Markdown("""
                        ## 环境变量管理
                        
                        在此处设置模型API密钥和其他服务凭证。这些信息将保存在本地的`.env`文件中，确保您的API密钥安全存储且不会上传到网络。正确设置API密钥对于OWL系统的功能至关重要, 可以按找工具需求灵活配置环境变量。
                        """)

                    # 主要内容分为两列布局
                    with gr.Row():
                        # 左侧列：环境变量管理控件
                        with gr.Column(scale=3):
                            with gr.Box(elem_classes="env-controls"):
                                # 环境变量表格 - 设置为可交互以直接编辑
                                gr.Markdown("""
                                <div style="background-color: #e7f3fe; border-left: 6px solid #2196F3; padding: 10px; margin: 15px 0; border-radius: 4px;">
                                  <strong>提示：</strong> 请确保运行cp .env_template .env创建本地.env文件，根据运行模块灵活配置所需环境变量
                                </div>
                                """)

                                # 增强版环境变量表格，支持添加和删除行
                                env_table = gr.Dataframe(
                                    headers=["变量名", "值", "获取指南"],
                                    datatype=[
                                        "str",
                                        "str",
                                        "html",
                                    ],  # 将最后一列设置为html类型以支持链接
                                    row_count=10,  # 增加行数，以便添加新变量
                                    col_count=(3, "fixed"),
                                    value=update_env_table,
                                    label="API密钥和环境变量",
                                    interactive=True,  # 设置为可交互，允许直接编辑
                                    elem_classes="env-table",
                                )

                                # 操作说明
                                gr.Markdown(
                                    """
                                <div style="background-color: #fff3cd; border-left: 6px solid #ffc107; padding: 10px; margin: 15px 0; border-radius: 4px;">
                                <strong>操作指南</strong>:
                                <ul style="margin-top: 8px; margin-bottom: 8px;">
                                  <li><strong>编辑变量</strong>: 直接点击表格中的"值"单元格进行编辑</li>
                                  <li><strong>添加变量</strong>: 在空白行中输入新的变量名和值</li>
                                  <li><strong>删除变量</strong>: 清空变量名即可删除该行</li>
                                  <li><strong>获取API密钥</strong>: 点击"获取指南"列中的链接获取相应API密钥</li>
                                </ul>
                                </div>
                                """,
                                    elem_classes="env-instructions",
                                )

                                # 环境变量操作按钮
                                with gr.Row(elem_classes="env-buttons"):
                                    save_env_button = gr.Button(
                                        "💾 保存更改",
                                        variant="primary",
                                        elem_classes="env-button",
                                    )
                                    refresh_button = gr.Button(
                                        "🔄 刷新列表", elem_classes="env-button"
                                    )

                                # 状态显示
                                env_status = gr.HTML(
                                    label="操作状态",
                                    value="",
                                    elem_classes="env-status",
                                )

        # 设置事件处理 - 简化版，不再需要module_dropdown参数
        run_button.click(
            fn=process_with_live_logs,
            inputs=[question_input],
            outputs=[token_count_output, status_output, text_display, image_display, html_display],
        )

        # 内容刷新相关事件处理
        refresh_text_button.click(
            fn=lambda: get_latest_logs(100, LOG_QUEUE), outputs=[text_display]
        )
        
        refresh_image_button.click(
            fn=lambda: get_latest_images(20), outputs=[image_display]
        )
        
        refresh_html_button.click(
            fn=lambda: get_latest_html(20), outputs=[html_display]
        )

        clear_content_button.click(
            fn=clear_log_file, 
            outputs=[text_display, image_display, html_display]
        )

        # 自动刷新控制
        def toggle_auto_refresh(enabled, interval=3):
            """控制自动刷新
            
            Args:
                enabled: 是否启用自动刷新
                interval: 刷新间隔（秒）
                
            Returns:
                gr.update: Gradio更新对象
            """
            if enabled:
                return gr.update(every=interval)
            else:
                return gr.update(every=0)

        auto_refresh_text.change(
            fn=lambda enabled: toggle_auto_refresh(enabled),
            inputs=[auto_refresh_text],
            outputs=[text_display],
        )
        
        auto_refresh_image.change(
            fn=lambda enabled: toggle_auto_refresh(enabled),
            inputs=[auto_refresh_image],
            outputs=[image_display],
        )
        
        auto_refresh_html.change(
            fn=lambda enabled: toggle_auto_refresh(enabled),
            inputs=[auto_refresh_html],
            outputs=[html_display],
        )

        # 初始设置自动刷新
        if True or gr.Checkbox.update_value:
            text_display.every = 3
            image_display.every = 3
            html_display.every = 3

        # 环境变量管理相关事件处理
        save_env_button.click(
            fn=save_env_table_changes,
            inputs=[env_table],
            outputs=[env_status],
        ).then(fn=update_env_table, outputs=[env_table])

        refresh_button.click(fn=update_env_table, outputs=[env_table])

    return app


# 主函数
def main():
    try:
        # 初始化日志系统
        global LOG_FILE
        LOG_FILE = setup_logging()
        logging.info("OWL Web应用程序启动")

        # 启动日志读取线程
        log_thread = threading.Thread(
            target=log_reader_thread, args=(LOG_FILE,), daemon=True
        )
        log_thread.start()
        logging.info("日志读取线程已启动")

        # 初始化.env文件（如果不存在）
        init_env_file()
        app = create_ui()

        app.queue()
        app.launch(share=False, server_name="127.0.0.1", server_port=7860)
    except Exception as e:
        logging.error(f"启动应用程序时发生错误: {str(e)}")
        print(f"启动应用程序时发生错误: {str(e)}")
        import traceback

        traceback.print_exc()

    finally:
        # 确保日志线程停止
        STOP_LOG_THREAD.set()
        STOP_REQUESTED.set()
        logging.info("应用程序关闭")


if __name__ == "__main__":
    main()


# 添加测试函数，用于手动添加HTML内容


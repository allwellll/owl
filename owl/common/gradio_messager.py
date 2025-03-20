import logging
import queue
import time
import os
from typing import Any

class GradioMessenger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(GradioMessenger, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """初始化消息队列和其他属性"""
        # 为不同类型的内容创建单独的队列和历史记录
        self.message_queues = {
            "text": queue.Queue(),
            "image": queue.Queue(),
            "html": queue.Queue()
        }
        self.chat_histories = {
            "text": [],
            "image": [],
            "html": []
        }
        self.last_update_time = time.time()
        logging.info("GradioMessenger已初始化")
    
    def send_message(self, role: str, content: Any, content_type: str = "text", add_to_log: bool = True):
        """发送消息到前端
        
        Args:
            role: 消息发送者角色 (如 "user", "assistant", "system")
            content: 消息内容
            content_type: 消息类型 ("text", "image", "html")
            add_to_log: 是否同时添加到日志系统
        """
        # 验证内容类型
        if content_type not in self.message_queues:
            content_type = "text"  # 默认为文本类型
        
        message = {
            "role": role, 
            "content": content, 
            "timestamp": time.time(),
            "content_type": content_type
        }
        
        # 添加到对应类型的队列和历史记录
        self.message_queues[content_type].put(message)
        self.chat_histories[content_type].append(message)
        
        # 限制历史记录长度，避免内存占用过大
        if len(self.chat_histories[content_type]) > 100:
            self.chat_histories[content_type] = self.chat_histories[content_type][-100:]
        
        # 同时记录到日志系统
        if add_to_log:
            # 对于图片和HTML内容，可能需要截断或特殊处理以避免日志过长
            log_content = content
            # if content_type == "image" and isinstance(content, str) and len(content) > 100:
                # log_content = f"{content[:100]}... [图片URL已截断]"
            # elif content_type == "html" and isinstance(content, str) and len(content) > 100:
                # log_content = f"{content[:100]}... [HTML内容已截断]"
            
            logging.info(f"消息 {len(self.chat_histories[content_type])}, 类型: {content_type}, 角色: {role}, 内容: {log_content}")
            logging.info(f"消息 {self.chat_histories[content_type]}")
    
    def get_messages(self, max_messages=50, clear_queue=True, content_type="text"):
        """获取队列中的消息
        
        Args:
            max_messages: 最大返回消息数
            clear_queue: 是否清空队列
            content_type: 消息类型 ("text", "image", "html")
            
        Returns:
            list: 消息列表
        """
        if content_type not in self.message_queues:
            return []
        
        messages = []
        try:
            # 从队列获取所有可用消息
            while not self.message_queues[content_type].empty() and len(messages) < max_messages:
                messages.append(self.message_queues[content_type].get_nowait())
                if not clear_queue:
                    # 如果不清空队列，将消息放回队列末尾
                    self.message_queues[content_type].put(messages[-1])
        except queue.Empty:
            pass
        
        # 确保消息被添加到历史记录中
        for msg in messages:
            if msg not in self.chat_histories[content_type]:
                self.chat_histories[content_type].append(msg)
        
        return messages
    
    def get_formatted_chat_history(self, max_messages=50, content_type="text"):
        """获取格式化的聊天历史记录
        
        Args:
            max_messages: 最大返回消息数
            content_type: 消息类型 ("text", "image", "html")
            
        Returns:
            根据内容类型返回不同格式:
            - text: 格式化的文本字符串
            - image: 图片路径列表
            - html: HTML内容字符串
        """
        if content_type not in self.chat_histories:
            if content_type == "text":
                return "暂无对话记录。"
            elif content_type == "image":
                return []
            elif content_type == "html":
                return "<div class='no-content'>暂无HTML内容xxxxx</div>"
            return None
        
        # 获取最新的消息
        recent_messages = self.chat_histories[content_type][-max_messages:] if self.chat_histories[content_type] else []
        
        # 从队列中获取尚未添加到历史记录的新消息
        new_messages = self.get_messages(max_messages, clear_queue=False, content_type=content_type)
        
        # 合并消息，确保不重复
        all_messages = []
        seen_contents = set()
        
        # 先添加历史消息
        for msg in recent_messages:
            content = str(msg.get("content", ""))
            if content not in seen_contents:
                all_messages.append(msg)
                seen_contents.add(content)
        
        # 再添加新消息
        for msg in new_messages:
            content = str(msg.get("content", ""))
            if content not in seen_contents:
                all_messages.append(msg)
                seen_contents.add(content)

        # if content_type == "html":
            # logging.info(f"HTML处理开始: 消息总数={len(all_messages)}")
            # for msg in all_messages:
                # logging.info(f"HTML消息: {msg}")

        if not all_messages:
            if content_type == "text":
                return "暂无对话记录。"
            elif content_type == "image":
                return []
            elif content_type == "html":
                return "<div class='no-content'>暂无HTML内容</div>"
        
        # 根据内容类型格式化消息
        if content_type == "text":
            # 格式化文本消息
            formatted_messages = []
            for msg in all_messages:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                
                # 格式化不同角色的消息
                # if role in ["user", "assistant", "system"]:
                formatted_messages.append(f"[{role.title()}]: {content}")
            
            return "\n\n".join(formatted_messages)
        
        elif content_type == "image":
            # 返回图片URL列表
            image_urls = []
            for msg in all_messages:
                content = msg.get("content", "")
                # 处理字符串类型的内容
                if content and isinstance(content, str):
                    # 检查是否为有效的图片URL或路径
                    if (content.startswith("http") and 
                        any(ext in content.lower() for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])) or \
                       (os.path.exists(content) and 
                        any(content.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp'])):
                        # 确保路径是绝对路径
                        if not content.startswith("http") and not os.path.isabs(content):
                            content = os.path.abspath(content)
                        image_urls.append(content)
                        # logging.info(f"添加图片到显示列表: {content}")
                # 直接处理非字符串类型的图片内容（如PIL图像、numpy数组等）
                elif content:
                    image_urls.append(content)
                    # logging.info(f"添加非字符串图片到显示列表")
            
            return image_urls
        
        elif content_type == "html":
            # 合并所有HTML内容
            html_contents = []
            
            for i, msg in enumerate(all_messages):
                content = msg.get("content", "")
                timestamp = msg.get("timestamp", time.time())
                formatted_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(timestamp))
                
                if content and isinstance(content, str):
                    # 添加时间戳和视觉包装
                    wrapped_content = f"""
                    <div class="message-wrapper" style="margin: 10px 0; padding: 10px; border: 1px solid #eee; border-radius: 5px;">
                        <div class="message-timestamp" style="color: #666; font-size: 0.8em; margin-bottom: 5px;">
                            {formatted_time}
                        </div>
                        <div class="message-content">
                            {content}
                        </div>
                    </div>
                    """
                    html_contents.append(wrapped_content)
            
            if not html_contents:
                return "<div class='no-content'>暂无HTML内容</div>"
            
            final_html = "\n".join(html_contents)
            return final_html
        
        return None
    
    def clear_messages(self):
        """清空所有消息队列和历史记录"""
        # 清空所有类型的队列
        for content_type in self.message_queues:
            while not self.message_queues[content_type].empty():
                try:
                    self.message_queues[content_type].get_nowait()
                except queue.Empty:
                    break
        
        # 清空所有类型的历史记录
        for content_type in self.chat_histories:
            self.chat_histories[content_type] = []
        
        logging.info("所有消息队列和历史记录已清空")


# 创建全局单例实例
gradio_messenger = GradioMessenger()
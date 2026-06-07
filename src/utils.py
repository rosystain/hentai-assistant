import os, json, re
import zipfile
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from glob import glob
from enum import Enum
from flask import Response

class TaskStatus(str, Enum):
    IN_PROGRESS = "进行中"
    COMPLETED = "完成"
    CANCELLED = "取消"
    ERROR = "错误"
    @classmethod
    def all(cls):
        return [item.value for item in cls]
    

def json_output(data):
    return json.dumps(data, indent=4, ensure_ascii=False)


def json_response(data, status=200):
    """
    生成 JSON 响应
    
    Args:
        data: 要返回的数据（字典或列表）
        status: HTTP 状态码，默认 200
    
    Returns:
        Flask Response 对象
    """
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )

# 检查目录是否存在
def check_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path

import threading
import time

_cover_download_lock = threading.Lock()

def download_cover(url: str, task_id: str, app_config: dict, logger=None) -> str:
    """下载封面并保存到本地缓存目录"""
    if not url:
        return url
        
    import requests
    cover_dir = check_dirs('./data/covers')
    
    # 获取扩展名，默认为 .jpg
    ext = ".jpg"
    if url.lower().endswith(('.png', '.webp', '.jpeg', '.gif', '.jpg')):
        ext = os.path.splitext(url.split('?')[0])[1].lower()
        
    save_path = os.path.join(cover_dir, f"{task_id}{ext}")
    
    # 如果本地已存在该任务的封面，直接跳过下载，避免重复请求和覆盖
    if os.path.exists(save_path):
        return f"/api/covers/{task_id}{ext}"
    
    try:
        proxies = None
        if app_config and app_config.get('PROXY_URL'):
            proxies = {
                'http': app_config['PROXY_URL'],
                'https': app_config['PROXY_URL']
            }
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': url
        }
        
        # 增加全局锁和延时，防止高并发导致 IP 被源站拉黑
        with _cover_download_lock:
            # 增加随机延时，降低被封禁风险
            import random
            time.sleep(random.uniform(0.5, 1.5))
            
            response = requests.get(url, headers=headers, proxies=proxies, timeout=10)
            response.raise_for_status()
            
            with open(save_path, 'wb') as f:
                f.write(response.content)
            
        return f"/api/covers/{task_id}{ext}"
    except Exception as e:
        if logger:
            logger.error(f"Failed to download cover {url} for task {task_id}: {e}")
        return url  # 下载失败则回退到原始 URL

# 判断是否为 URL
def is_url(text):
    # 正则表达式用于匹配 URL
    url_pattern = re.compile(r'(https?://[^\s]+)')
    return re.match(url_pattern, text) is not None

# 验证 ZIP 文件完整性
def is_valid_zip(path: str) -> bool:
    if not path or not os.path.exists(path):
        return False
    try:
        with zipfile.ZipFile(path, "r") as zf:
            return zf.testzip() is None
    except (FileNotFoundError, zipfile.BadZipFile):
        return False

# 移除字符串中的表情符号
def remove_emoji(text):
    return ''.join(
        c for c in text
        if not unicodedata.category(c).startswith('So')
    )

def extract_parody(text, translator):
    # 匹配末尾是 (xxx) [后缀] [后缀]... 的情况，提取 () 内内容
    match = re.search(r'\((?!\d+$)([^)]+)\)\s*(?:\[[^\]]+\]\s*)+$', text)
    if match:
        parody = match.group(1).strip()
    else:
        # 匹配末尾直接是 () 的情况
        match = re.search(r'\((?!\d+$)([^)]+)\)\s*$', text)
        parody = match.group(1).strip().lower() if match else None

    if parody:
        # 拆分日文顿号并去掉每个部分前后空格
        if '、' in parody:
            parts = [part.strip() for part in parody.split('、')]
            # 分别翻译
            translated_parts = [translator.get_translation(part.strip(), 'parody') for part in parts]
            parody_translated = ', '.join(translated_parts)
        else:
            parody_translated = translator.get_translation(parody.strip(), 'parody')
        return parody_translated
    return None



def get_task_logger(task_id=None):
    MAX_UUID_LOG_FILES = 5
    MAX_APP_LOG_FILES = 3
    LOG_DIR = "logs"
    os.makedirs(LOG_DIR, exist_ok=True)

    if task_id:
        # uuid 日志轮转，最多保留5个
        log_files = sorted(
            [f for f in glob(os.path.join(LOG_DIR, "*.log")) if not f.endswith("app.log")],
            key=os.path.getmtime
        )
        while len(log_files) >= MAX_UUID_LOG_FILES:
            os.remove(log_files[0])
            log_files = sorted(
                [f for f in glob(os.path.join(LOG_DIR, "*.log")) if not f.endswith("app.log")],
                key=os.path.getmtime
            )
        logger_name = str(task_id)
        log_path = os.path.join(LOG_DIR, f"{task_id}.log")
        mode = 'a'
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.handlers = []
        fh = logging.FileHandler(log_path, mode=mode, encoding='utf-8')
    else:
        # app.log 轮转，最多3份
        logger_name = "app"
        log_path = os.path.join(LOG_DIR, "app.log")
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.INFO)
        logger.handlers = []
        fh = RotatingFileHandler(
            log_path,
            mode='a',
            maxBytes=2 * 1024 * 1024,  # 每个日志最大2MB，可根据需要调整
            backupCount=MAX_APP_LOG_FILES,
            encoding='utf-8'
        )

    file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    fh.setFormatter(file_formatter)
    logger.addHandler(fh)

    # 控制台输出
    ch = logging.StreamHandler()
    console_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    ch.setFormatter(console_formatter)
    logger.addHandler(ch)

    return logger

def parse_gallery_url(url: str) -> tuple[int | None, str | None]:
    """从 E-Hentai/ExHentai 画廊 URL 中解析 gid 和 token"""
    if not isinstance(url, str):
        return None, None
    match = re.search(r'/g/(\d+)/([a-f0-9]{10})', url)
    if match:
        gid = int(match.group(1))
        token = match.group(2)
        return gid, token
    return None, None

def parse_interval_to_hours(interval_str):
    """
    解析 interval 配置，支持多种常见的时间单位格式
    返回小时数（浮点数），如果格式无效返回 None
    
    支持的格式:
        分钟: '30m', '30min', '30mins', '30minute', '30minutes'
        小时: '6h', '6hr', '6hrs', '6hour', '6hours'
        天:   '1d', '1day', '1days'
    
    示例:
        '30m' / '30min' -> 0.5
        '6h' / '6hours' -> 6.0
        '1d' / '1day' -> 24.0
        '12' -> None (缺少单位)
    """
    interval_str = str(interval_str).strip().lower()
    
    # 使用正则表达式提取数字和单位
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-z]+)$', interval_str)
    
    if not match:
        # 没有匹配到单位
        logging.warning(f"Invalid interval format ('{interval_str}'): missing time unit. Supported: m/min/h/hour/d/day")
        return None
    
    try:
        value = float(match.group(1))
        unit = match.group(2)
        
        # 分钟
        if unit in ('m', 'min', 'mins', 'minute', 'minutes'):
            return value / 60
        # 小时
        elif unit in ('h', 'hr', 'hrs', 'hour', 'hours'):
            return value
        # 天
        elif unit in ('d', 'day', 'days'):
            return value * 24
        else:
            logging.warning(f"Invalid interval format ('{interval_str}'): unknown unit '{unit}'. Supported: m/min/h/hour/d/day")
            return None
    except (ValueError, TypeError, AttributeError) as e:
        logging.warning(f"Invalid interval format ('{interval_str}'). Error: {e}")
        return None

def chinese_number_to_arabic(cn_num: str) -> str:
    """
    将简单的中文数字转换为阿拉伯数字字符串
    仅支持: 一、二、三、四、五、六、七、八、九、十 以及它们的组合
    返回字符串形式的数字,如果无法转换则返回 None
    """
    cn_to_num = {
        '一': 1, '二': 2, '三': 3, '四': 4, '五': 5,
        '六': 6, '七': 7, '八': 8, '九': 9, '十': 10,
        '壹': 1, '贰': 2, '叁': 3, '肆': 4, '伍': 5,
        '陆': 6, '柒': 7, '捌': 8, '玖': 9, '拾': 10
    }
    
    cn_num = cn_num.strip()
    
    # 单个汉字直接转换
    if len(cn_num) == 1:
        return str(cn_to_num.get(cn_num))
    
    # 处理 "十X" (10-19)
    if cn_num.startswith(('十', '拾')) and len(cn_num) == 2:
        unit = cn_to_num.get(cn_num[1])
        if unit:
            return str(10 + unit)
    
    # 处理 "X十" (20, 30, ..., 90)
    if cn_num.endswith(('十', '拾')) and len(cn_num) == 2:
        tens = cn_to_num.get(cn_num[0])
        if tens and tens < 10:
            return str(tens * 10)
    
    # 处理 "X十Y" (21-99)
    if len(cn_num) == 3 and cn_num[1] in ['十', '拾']:
        tens = cn_to_num.get(cn_num[0])
        unit = cn_to_num.get(cn_num[2])
        if tens and unit and tens < 10 and unit < 10:
            return str(tens * 10 + unit)
    
    # 无法转换
    return None

def sanitize_filename(s: str) -> str:
    """移除文件名中的非法字符"""
    return re.sub(r'[\\/:*?"<>|]', '_', s)

def truncate_filename(title: str, suffix: str, max_bytes: int = 255) -> str:
    """
    截断文件名以确保不超过文件系统限制。
    
    各平台文件系统限制：
    - Windows (NTFS): 255 字符
    - Linux (ext4): 255 字节
    - macOS (HFS+/APFS): 255 字符
    
    为了兼容所有平台，使用 255 字节作为限制。
    如果文件名过长，从标题中间截断并用 "..." 替换。
    
    Args:
        title: 已经过 sanitize 的标题
        suffix: 文件名后缀，如 " [123456].zip"
        max_bytes: 最大字节数限制，默认 255
        
    Returns:
        截断后的完整文件名
    """
    filename = f"{title}{suffix}"
    filename_bytes = filename.encode('utf-8')
    
    if len(filename_bytes) <= max_bytes:
        return filename
    
    # 计算后缀的字节数和省略符号的字节数
    suffix_bytes = len(suffix.encode('utf-8'))
    ellipsis = "..."
    ellipsis_bytes = len(ellipsis.encode('utf-8'))  # 3 字节
    
    # 标题可用的最大字节数
    available_bytes = max_bytes - suffix_bytes - ellipsis_bytes
    
    if available_bytes <= 0:
        # 如果后缀本身就超过限制，只能截断后缀（极端情况）
        return filename[:max_bytes]
    
    # 从标题两端保留字符，中间用 ... 替换
    # 前半部分和后半部分各占一半
    half_bytes = available_bytes // 2
    
    # 从前面截取字符直到接近 half_bytes
    front_chars = ""
    front_byte_count = 0
    for char in title:
        char_bytes = len(char.encode('utf-8'))
        if front_byte_count + char_bytes > half_bytes:
            break
        front_chars += char
        front_byte_count += char_bytes
    
    # 从后面截取字符直到接近剩余可用字节数
    remaining_bytes = available_bytes - front_byte_count
    back_chars = ""
    back_byte_count = 0
    for char in reversed(title):
        char_bytes = len(char.encode('utf-8'))
        if back_byte_count + char_bytes > remaining_bytes:
            break
        back_chars = char + back_chars
        back_byte_count += char_bytes
    
    truncated_title = f"{front_chars}{ellipsis}{back_chars}"
    return f"{truncated_title}{suffix}"

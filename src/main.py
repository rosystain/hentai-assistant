import os, re, shutil, sqlite3
import json, html
from datetime import datetime, timezone
import subprocess # 导入 subprocess 模块
import sys # 导入 sys 模块
import functools
import jinja2


from flask import Flask, request, redirect, send_from_directory, Response
from flask_cors import CORS
import concurrent.futures
import langcodes
import threading
from io import StringIO
import logging
from logging.handlers import RotatingFileHandler

# import local modules
from providers import komga
from providers import aria2
from providers import ehentai
from providers import nhentai
from providers import hitomi
from providers import hdoujin
from providers.ehtranslator import EhTagTranslator
from utils import check_dirs, is_valid_zip, TaskStatus, parse_gallery_url, parse_interval_to_hours, sanitize_filename, truncate_filename
from notification import notify
import cbztool
from database import task_db
from config import load_config, save_config
from metadata_extractor import MetadataExtractor, parse_filename
from migrate import migrate_ini_to_yaml
from scheduler import init_scheduler, update_scheduler_jobs

# import route modules (Blueprint)
from routes.ehentai import bp as ehentai_bp
from routes.task import bp as task_bp
from routes.config import bp as config_bp
from routes.hdoujin import bp as hdoujin_bp
from routes.download import bp as download_bp
from routes.komga import bp as komga_bp
from routes.rss import rss_bp, init_rss_cache
from routes.scheduler import bp as scheduler_bp

# 全局变量用于存储子进程对象
notification_process = None
eh_translator = None
metadata_extractor = None

def start_notification_process(app_instance=None):
    """启动 notification.py 子进程"""
    global notification_process
    
    # 如果没有传入 app_instance，使用模块级的 app
    if app_instance is None:
        app_instance = app
    
    if notification_process and notification_process.poll() is None:
        global_logger.info("notification.py 进程已在运行中。")
        # 同时更新 app_instance.config
        app_instance.config['NOTIFICATION_PROCESS'] = notification_process
        app_instance.config['NOTIFICATION_PROCESS_PID'] = notification_process.pid
        return

    try:
        global_logger.info("正在启动 notification.py 子进程...")
        notification_process = subprocess.Popen([
            sys.executable,
            'src/notification.py'
        ])
        global_logger.info(f"notification.py 已作为子进程启动, PID: {notification_process.pid}")

        # 同时更新 app_instance.config，确保 config 路由能读取到
        app_instance.config['NOTIFICATION_PROCESS'] = notification_process
        app_instance.config['NOTIFICATION_PROCESS_PID'] = notification_process.pid
    except Exception as e:
        global_logger.error(f"启动 notification.py 失败: {e}")
        notification_process = None
        # 清除 app_instance.config 中的状态
        app_instance.config['NOTIFICATION_PROCESS'] = None
        app_instance.config['NOTIFICATION_PROCESS_PID'] = None

def stop_notification_process(app_instance=None):
    """停止 notification.py 子进程"""
    global notification_process
    
    # 如果没有传入 app_instance，使用模块级的 app
    if app_instance is None:
        app_instance = app
    
    if notification_process and notification_process.poll() is None:
        global_logger.info(f"正在终止 notification.py 子进程, PID: {notification_process.pid}")
        notification_process.terminate()
        try:
            notification_process.wait(timeout=5)
            global_logger.info("notification.py 子进程已终止。")
        except subprocess.TimeoutExpired:
            global_logger.warning("notification.py 子进程在超时时间内未能终止，尝试强制终止。")
            notification_process.kill()
            notification_process.wait()
            global_logger.info("notification.py 子进程已强制终止。")
        finally:
            notification_process = None
            # 同时清除 app_instance.config 中的状态
            app_instance.config['NOTIFICATION_PROCESS'] = None
            app_instance.config['NOTIFICATION_PROCESS_PID'] = None


# 配置 Flask 以服务 Vue.js 静态文件
# 在生产环境中，Vue.js 应用会被构建到 `webui/dist` 目录
# Flask 将从这个目录提供静态文件
app = Flask(
    __name__,
    static_folder='../webui/dist', # Vue.js 构建后的完整目录（包含index.html和assets）
    static_url_path='/static-assets' # 将静态文件URL前缀改为/static-assets，避免与前端路由冲突
)
CORS(app) # 在 Flask 应用中启用 CORS
# 过滤掉 /api/task_stats 的访问日志
class StatsFilter(logging.Filter):
    def filter(self, record):
        return 'GET /api/task_stats' not in record.getMessage()

logging.getLogger('werkzeug').addFilter(StatsFilter())
# 设置5001端口为默认端口

# 创建一个线程池用于并发处理任务
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

tasks = {}
tasks_lock = threading.Lock()

class TaskInfo:
    def __init__(self, future, logger, log_buffer):
        self.future = future
        self.logger = logger
        self.log_buffer = log_buffer
        self.status = TaskStatus.IN_PROGRESS  # "完成"、"取消"、"错误"
        self.error = None
        self.filename = None # 初始 filename 为 None
        self.progress = 0  # 进度百分比 0-100
        self.downloaded = 0  # 已下载字节数
        self.total_size = 0  # 总字节数
        self.speed = 0  # 下载速度 B/s
        self.cancelled = False  # 取消标志
        self.aria2_gid = None  # Aria2 下载任务的 gid

class SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'

# 日志初始化
LOG_FILE = "./data/app.log"

def json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )

def add_console_handler(logger, formatter):
    """Adds a console handler to the logger."""
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

def init_global_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        
        # Handler 1: 写入文件
        file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Handler 2: 写入终端
        add_console_handler(logger, formatter)
    return logger

global_logger = init_global_logger()

def get_task_logger(task_id):
    log_buffer = StringIO()
    logger = logging.getLogger(f"task_{task_id}")
    logger.setLevel(logging.INFO)

    # 清除旧的 handlers，以防重试任务时重复添加
    if logger.hasHandlers():
        logger.handlers.clear()

    formatter = logging.Formatter(f'%(asctime)s [%(levelname)s] [task:{task_id}] %(message)s')

    # Handler 1: 写入内存缓冲区 (用于 API)
    buffer_handler = logging.StreamHandler(log_buffer)
    buffer_handler.setFormatter(formatter)
    logger.addHandler(buffer_handler)

    # Handler 2: 写入终端 (用于 Docker logs)
    add_console_handler(logger, formatter)

    # 阻止日志向上传播到 root logger，避免 werkzeug 环境下重复输出
    logger.propagate = False

    return logger, log_buffer

def update_eh_funds(eh_funds):
    """更新 eh_funds 到 app.config 和数据库"""
    if eh_funds is not None:
        # eh_funds 现在是包含 GP 和 Credits 的字典
        app.config['EH_FUNDS'] = eh_funds
        task_db.set_global_state('eh_funds', json.dumps(eh_funds))
        gp = eh_funds.get('GP', '-')
        credits = eh_funds.get('Credits', '-')
        global_logger.info(f"E-Hentai 余额已更新: GP={gp}, Credits={credits}")

def check_config(app_instance=None):
    """检查并加载应用配置，并根据配置变化管理通知子进程。"""
    global notification_process, eh_translator, metadata_extractor
    
    # 如果没有传入 app_instance，使用模块级的 app
    if app_instance is None:
        app_instance = app
    
    config_data = load_config()

    # 记录 Komga 的旧状态
    was_komga_enabled = app_instance.config.get('KOMGA_TOGGLE', False)

    # 通用设置
    general = config_data.get('general', {})
    # 端口配置:优先从环境变量读取,默认5001
    app_instance.config['PORT'] = int(os.environ.get('BACKEND_API_PORT', 5001))
    app_instance.config['KEEP_TORRENTS'] = general.get('keep_torrents', False)
    app_instance.config['KEEP_ORIGINAL_FILE'] = general.get('keep_original_file', False)
    app_instance.config['PREFER_JAPANESE_TITLE'] = general.get('prefer_japanese_title', True)
    app_instance.config['MOVE_PATH'] = str(general.get('move_path', '')).rstrip('/') or None

    # 高级设置
    advanced = config_data.get('advanced', {})
    app_instance.config['TAGS_TRANSLATION'] = advanced.get('tags_translation', False)
    app_instance.config['REMOVE_ADS'] = advanced.get('remove_ads', False)
    app_instance.config['AGGRESSIVE_SERIES_DETECTION'] = advanced.get('aggressive_series_detection', False)
    app_instance.config['OPENAI_SERIES_DETECTION'] = advanced.get('openai_series_detection', False)
    app_instance.config['PREFER_OPENAI_SERIES'] = advanced.get('prefer_openai_series', False)

    # E-Hentai 设置
    ehentai_config = config_data.get('ehentai', {})
    app_instance.config['EH_IPB_MEMBER_ID'] = ehentai_config.get('ipb_member_id', '')
    app_instance.config['EH_IPB_PASS_HASH'] = ehentai_config.get('ipb_pass_hash', '')

    # E-Hentai 收藏夹同步设置 (扁平化结构)
    app_instance.config['EH_FAV_SYNC_ENABLED'] = ehentai_config.get('favorite_sync', False)
    # 解析 favorite_sync_interval 配置并转换为小时数（保持浮点数以支持分钟级精度）
    fav_interval = ehentai_config.get('favorite_sync_interval', '6h')
    interval_hours = parse_interval_to_hours(fav_interval)
    if interval_hours is None:
        logging.error(f"Invalid 'ehentai.favorite_sync_interval': {fav_interval}. Must include time unit (m/h/d). Using default 6h.")
        interval_hours = 6.0
    app_instance.config['EH_FAV_SYNC_INTERVAL'] = interval_hours
    app_instance.config['EH_FAV_AUTO_DOWNLOAD'] = ehentai_config.get('auto_download_favorites', False)

    # H@H 监控设置
    app_instance.config['HATH_CHECK_ENABLED'] = ehentai_config.get('hath_check_enabled', False)
    # 解析 hath_check_interval 并转换为分钟数
    hath_interval = ehentai_config.get('hath_check_interval', '30m')
    hath_interval_hours = parse_interval_to_hours(hath_interval)
    if hath_interval_hours is None:
        logging.error(f"Invalid 'ehentai.hath_check_interval': {hath_interval}. Must include time unit (m/h/d). Using default 30m.")
        hath_interval_hours = 0.5  # 30分钟
    
    # 转换为分钟，并限制最小间隔为 5 分钟
    hath_interval_minutes = hath_interval_hours * 60
    if hath_interval_minutes < 5:
        logging.warning(f"'ehentai.hath_check_interval' too small ({hath_interval_minutes:.2f} minutes), setting to minimum 5 minutes.")
        hath_interval_minutes = 5
    app_instance.config['HATH_CHECK_INTERVAL'] = int(hath_interval_minutes)

    # 首次扫描页数：0 表示全量扫描，其他数字表示扫描指定页数
    try:
        initial_scan_pages = int(ehentai_config.get('initial_scan_pages', 1))
        app_instance.config['EH_FAV_INITIAL_SCAN_PAGES'] = max(0, initial_scan_pages)  # 确保非负数
    except (ValueError, TypeError):
        app_instance.config['EH_FAV_INITIAL_SCAN_PAGES'] = 1
        logging.warning("Invalid 'ehentai.initial_scan_pages'. Falling back to default 1 page.")

    # favcat_whitelist 支持空列表 (所有), 或 [0,1,2] (特定)
    favcat_whitelist = ehentai_config.get('favcat_whitelist', [])
    if not favcat_whitelist or favcat_whitelist == []:
        app_instance.config['EH_FAV_SYNC_FAVCAT'] = list(map(str, range(10)))  # 空列表对应 0-9
    else:
        # 将列表中的元素转换为字符串
        app_instance.config['EH_FAV_SYNC_FAVCAT'] = [str(cat).strip() for cat in favcat_whitelist]
    

    # nhentai 设置
    nhentai_config = config_data.get('nhentai', {})
    nhentai_cookie = nhentai_config.get('cookie', '')
    app_instance.config['NHENTAI_COOKIE'] = {"cookie": nhentai_cookie} if nhentai_cookie else {"cookie": ""}

    # 初始化 E-Hentai 工具类并存储在 app.config 中
    if 'EH_TOOLS' not in app.config:
        app_instance.config['EH_TOOLS'] = ehentai.EHentaiTools(
            ipb_member_id=app_instance.config['EH_IPB_MEMBER_ID'],
            ipb_pass_hash=app_instance.config['EH_IPB_PASS_HASH'],
            logger=global_logger
        )
    else:
        # 如果已存在，重新创建实例以应用新配置
        app_instance.config['EH_TOOLS'] = ehentai.EHentaiTools(
            ipb_member_id=app_instance.config['EH_IPB_MEMBER_ID'],
            ipb_pass_hash=app_instance.config['EH_IPB_PASS_HASH'],
            logger=global_logger
        )

    eh = app_instance.config['EH_TOOLS']
    nh = nhentai.NHentaiTools(cookie=app_instance.config['NHENTAI_COOKIE'], logger=global_logger)
    
    # E-Hentai 验证
    eh_valid, exh_valid, eh_funds = eh.is_valid_cookie()
    if eh_valid or exh_valid:
        # 预热收藏夹列表缓存
        global_logger.info("正在预获取 E-Hentai 收藏夹列表...")
        eh.get_favcat_list()
    # 更新 E-Hentai 和 ExHentai 验证状态
    app_instance.config['EH_VALID'] = eh_valid
    app_instance.config['EXH_VALID'] = exh_valid
    update_eh_funds(eh_funds)
    
    # nhentai 验证
    nh_toggle = nh.is_valid_cookie()
    
    # hdoujin 设置 - 使用统一的刷新函数
    from providers.hdoujin import refresh_and_sync_hdoujin_config
    hd_toggle = refresh_and_sync_hdoujin_config(app.config, global_logger)

    # Aria2 RPC 设置
    aria2_config = config_data.get('aria2', {})
    aria2_enable = aria2_config.get('enable', False)

    if aria2_enable:
        global_logger.info("开始测试 Aria2 RPC 的连接")
        app_instance.config['ARIA2_SERVER'] = str(aria2_config.get('server', '')).rstrip('/')
        app_instance.config['ARIA2_TOKEN'] = str(aria2_config.get('token', ''))
        app_instance.config['ARIA2_DOWNLOAD_DIR'] = str(aria2_config.get('download_dir', '')).rstrip('/') or None
        app_instance.config['REAL_DOWNLOAD_DIR'] = str(aria2_config.get('mapped_dir', '')).rstrip('/') or app_instance.config['ARIA2_DOWNLOAD_DIR']

        rpc = aria2.Aria2RPC(url=app_instance.config['ARIA2_SERVER'], token=app_instance.config['ARIA2_TOKEN'], logger=global_logger)
        try:
            result = rpc.get_global_stat()
            if 'result' in result:
                global_logger.info("Aria2 RPC 连接正常")
                aria2_toggle = True
            else:
                global_logger.error("Aria2 RPC 连接异常, 种子下载功能将不可用")
                aria2_toggle = False
        except Exception as e:
            global_logger.error(f"Aria2 RPC 连接异常: {e}")
            aria2_toggle = False
    else:
        global_logger.info("Aria2 RPC 功能未启用")
        aria2_toggle = False
        app_instance.config['ARIA2_SERVER'] = ''
        app_instance.config['ARIA2_TOKEN'] = ''
        app_instance.config['ARIA2_DOWNLOAD_DIR'] = None
        app_instance.config['REAL_DOWNLOAD_DIR'] = None

    # Komga API 设置
    komga_config = config_data.get('komga', {})
    komga_enable = komga_config.get('enable', False)

    if komga_enable:
        global_logger.info("开始测试 Komga API 的连接")
        app_instance.config['KOMGA_SERVER'] = str(komga_config.get('server', '')).rstrip('/')
        app_instance.config['KOMGA_USERNAME'] = str(komga_config.get('username', ''))
        app_instance.config['KOMGA_PASSWORD'] = str(komga_config.get('password', ''))
        app_instance.config['KOMGA_LIBRARY_ID'] = str(komga_config.get('library_id', ''))

        kmg = komga.KomgaAPI(server=app_instance.config['KOMGA_SERVER'], username=app_instance.config['KOMGA_USERNAME'], password=app_instance.config['KOMGA_PASSWORD'],  logger=global_logger)
        try:
            library = kmg.get_libraries(library_id=app_instance.config['KOMGA_LIBRARY_ID'])
            if library.status_code == 200:
                global_logger.info("Komga API 连接成功")
                komga_toggle = True
            else:
                # 连接失败时，如果之前是启用的，保持启用状态
                previous_toggle = app_instance.config.get('KOMGA_TOGGLE', False)
                if previous_toggle:
                    global_logger.warning("Komga API 连接异常，但保持功能启用（之前状态为启用）")
                    komga_toggle = True
                else:
                    komga_toggle = False
                    global_logger.error("Komga API 连接异常, 相关功能将不可用")
        except Exception as e:
            # 连接异常时，如果之前是启用的，保持启用状态
            previous_toggle = app_instance.config.get('KOMGA_TOGGLE', False)
            if previous_toggle:
                global_logger.warning(f"Komga API 连接异常: {e}，但保持功能启用（之前状态为启用）")
                komga_toggle = True
            else:
                global_logger.error(f"Komga API 连接异常: {e}")
                komga_toggle = False
    else:
        global_logger.info("Komga API 功能未启用")
        komga_toggle = False
        app_instance.config['KOMGA_SERVER'] = ''
        app_instance.config['KOMGA_USERNAME'] = ''
        app_instance.config['KOMGA_PASSWORD'] = ''
        app_instance.config['KOMGA_LIBRARY_ID'] = ''

    # Komga URL 索引同步设置
    app_instance.config['KOMGA_INDEX_SYNC_ENABLED'] = komga_config.get('index_sync', False)
    index_sync_interval = komga_config.get('index_sync_interval', '6h')
    index_sync_interval_hours = parse_interval_to_hours(index_sync_interval)
    if index_sync_interval_hours is None:
        logging.error(f"Invalid 'komga.index_sync_interval': {index_sync_interval}. Must include time unit (m/h/d). Using default 6h.")
        index_sync_interval_hours = 6.0
    app_instance.config['KOMGA_INDEX_SYNC_INTERVAL'] = index_sync_interval_hours

    is_komga_enabled = komga_toggle

    # 只有在主工作进程中才管理子进程的生命周期，以避免 reloader 重复启动
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == 'true':
        is_config_update = app.config.get('CHECKING_CONFIG', False)

        if not is_komga_enabled:
            if was_komga_enabled:
                global_logger.info("Komga 功能已禁用，正在停止通知监听器...")
                stop_notification_process(app_instance)
        else:
            if not was_komga_enabled:
                global_logger.info("Komga 功能已启用，正在启动通知监听器...")
                start_notification_process(app_instance)
            elif is_config_update:
                global_logger.info("配置已更新，正在重启 Komga 通知监听器以应用更改...")
                stop_notification_process(app_instance)
                start_notification_process(app_instance)

    app_instance.config['NH_TOGGLE'] = nh_toggle
    app_instance.config['HD_TOGGLE'] = hd_toggle
    app_instance.config['ARIA2_TOGGLE'] = aria2_toggle
    app_instance.config['KOMGA_TOGGLE'] = komga_toggle
    app_instance.config['CHECKING_CONFIG'] = False

    # 通知设置
    notification_config = config_data.get('notification', {})
    
    # 动态检查是否有任何 notifier 被启用
    is_any_notifier_enabled = any(
        details.get('enable') for name, details in notification_config.items()
    )
    
    # 将检查结果作为 'enable' 键添加到字典中
    notification_config['enable'] = is_any_notifier_enabled
    app_instance.config['NOTIFICATION'] = notification_config

    if is_any_notifier_enabled:
        global_logger.info("通知服务功能已启用 (至少有一个通知器处于开启状态)")
    else:
        global_logger.info("通知服务功能未启用 (没有活动的通知器)")
        
    # Openai 设置
    openai_config = config_data.get('openai', {})
    app_instance.config['OPENAI_API_KEY'] = str(openai_config.get('api_key', '')).strip()
    app_instance.config['OPENAI_BASE_URL'] = str(openai_config.get('base_url', '')).strip().rstrip('/')
    app_instance.config['OPENAI_MODEL'] = str(openai_config.get('model', '')).strip()
    if app_instance.config['OPENAI_API_KEY'] and app_instance.config['OPENAI_BASE_URL'] and app_instance.config['OPENAI_MODEL']:
        global_logger.info("OpenAI 配置已设置")
        app_instance.config['OPENAI_TOGGLE'] = True
    else:

        app_instance.config['OPENAI_TOGGLE'] = False
    
    # ComicInfo 设置
    app_instance.config['COMICINFO'] = config_data.get('comicinfo', {})

    eh_translator = EhTagTranslator(enable_translation=app_instance.config.get('TAGS_TRANSLATION', True))
    metadata_extractor = MetadataExtractor(app_instance.config, eh_translator)

    # 从数据库加载 eh_funds
    eh_funds_json = task_db.get_global_state('eh_funds')
    if eh_funds_json:
        try:
            app_instance.config['EH_FUNDS'] = json.loads(eh_funds_json)
            global_logger.debug(f"从数据库加载 eh_funds: {app_instance.config['EH_FUNDS']}")
        except json.JSONDecodeError:
            global_logger.error("从数据库加载 eh_funds 失败：无效的 JSON 格式")

    # 更新调度器任务（配置更新时总是需要更新）
    global_logger.info("准备调用 update_scheduler_jobs...")
    update_scheduler_jobs(app_instance)
    global_logger.info("update_scheduler_jobs 调用完成")

def get_eh_mode(config, mode):
    aria2_enabled = config.get('ARIA2_TOGGLE', False)
    eh_valid = config.get('EH_VALID', False)
    
    # 用户明确指定了模式
    if mode in ("torrent", "1"):
        return "torrent"
    elif mode in ("archive", "0"):
        return "archive"
    
    # 自动决定：有 aria2 优先 torrent，否则用 archive
    if aria2_enabled:
        return "torrent"
    elif eh_valid:
        return "archive"
    else:
        return "torrent"

def send_to_aria2(url=None, torrent=None, dir=None, out=None, logger=None, task_id=None, tasks=None, tasks_lock=None):
    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id, tasks, tasks_lock)

    rpc = aria2.Aria2RPC(app.config.get('ARIA2_SERVER'), app.config.get('ARIA2_TOKEN'))
    result = None
    if url != None:
        result = rpc.add_uri(url, dir=dir, out=out)
        if logger: logger.info(result)
    elif torrent != None:
        result = rpc.add_torrent(torrent, dir=dir, out=out)
        if not app.config.get('KEEP_TORRENTS') == True:
            os.remove(torrent)
        if logger: logger.info(result)
    else:
        if logger: logger.error("send_to_aria2: 必须提供 url 或 torrent 参数")
        return None

    if result is None or 'result' not in result:
        if logger: logger.error("send_to_aria2: 无法获取有效的下载任务结果")
        return None

    gid = result['result']

    # 保存 gid 到任务信息中
    if task_id and tasks and tasks_lock:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].aria2_gid = gid
                if logger:
                    logger.info(f"Aria2 任务已启动，gid: {gid}")

    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id, tasks, tasks_lock)

    # 监视 aria2 的下载进度
    file = rpc.listen_status(gid, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
    
    # 下载完成或取消后，清除 gid
    if task_id and tasks and tasks_lock:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].aria2_gid = None
    if file == None:
        return None
    else:
        filename = os.path.basename(file)
        real_dir = app.config.get('REAL_DOWNLOAD_DIR') or '.'
        if filename.lower().endswith(('.7z', '.zip', '.cbz')):
            local_file_path = os.path.join(real_dir, filename)
        else:
            local_file_path = os.path.join(real_dir, os.path.basename(os.path.dirname(file)))

    # 完成下载后, 为压缩包添加元数据
    if os.path.exists(file):
        print(f"下载完成: {local_file_path}")
        if logger: logger.info(f"下载完成: {local_file_path}")
    return local_file_path


def check_task_cancelled(task_id, tasks=None, tasks_lock=None):
    # 如果没有传入 tasks 和 tasks_lock，从 app.config 获取
    if tasks is None:
        tasks = app.config.get('TASKS', {})
    if tasks_lock is None:
        tasks_lock = app.config.get('TASKS_LOCK')
    
    if tasks_lock:
        with tasks_lock:
            task = tasks.get(task_id)
            if task and task.cancelled:
                raise Exception("Task was cancelled by user")

def try_fallback_download(gmetadata, logger=None):
    """
    尝试回退下载方案：hdoujin -> hitomi -> nhentai

    Args:
        gmetadata: ehentai 元数据
        logger: 日志记录器

    Returns:
        tuple: (url, tool) 或 (None, None)
    """
    if not gmetadata:
        return None, None

    category = gmetadata.get('category', '').lower()
    if category not in ['doujinshi', 'manga', 'artistcg', 'gamecg', 'imageset']:
        return None, None

    # 首先尝试 hdoujin
    try:
        title = gmetadata.get('title') or gmetadata.get('title_jpn')
        if not title:
            return None, None

        # 使用 hdoujin 工具进行搜索
        hdoujin_tool = hdoujin.HDoujinTools(
            session_token=app.config['HDOUJIN_SESSION_TOKEN'],
            refresh_token=app.config['HDOUJIN_REFRESH_TOKEN'],
            clearance_token=app.config['HDOUJIN_CLEARANCE_TOKEN'],
            user_agent=app.config['HDOUJIN_USER_AGENT'],
            logger=logger
        )

        # 获取原始标题和语言信息用于更精确的匹配
        original_title = gmetadata.get('title_jpn')
        language = None
        for tag in gmetadata.get('tags', []):
            if isinstance(tag, str):
                if tag.startswith('language:'):
                    lang_name = tag.split(':', 1)[1]
                    if lang_name not in ['translated', 'rewrite', 'speechless', 'text cleaned']:
                        language = lang_name
                        break

        hdoujin_id, hdoujin_key = hdoujin_tool.search_by_title(title, original_title, language)
        if logger:
            logger.info(f"优先尝试 hdoujin 搜索: title='{title}', original_title='{original_title}', language='{language}' -> hdoujin_id={hdoujin_id}")

        if hdoujin_id and hdoujin_key:
            if logger:
                logger.info(f"找到匹配的 hdoujin 画廊 {hdoujin_id}，切换到 hdoujin 下载")

            hdoujin_url = f'https://hdoujin.org/g/{hdoujin_id}/{hdoujin_key}/'

            return hdoujin_url, hdoujin_tool

    except Exception as e:
        import traceback
        if logger:
            logger.warning(f"hdoujin 回退失败: {e}")
            logger.warning(f"完整错误信息: {traceback.format_exc()}")

    # 如果 hdoujin 失败，回退到 hitomi
    try:
        gid = gmetadata.get('gid')
        if gid:
            hitomi_tool = hitomi.HitomiTools(logger=logger)

            # 先检查画廊是否存在
            try:
                gallery_data = hitomi_tool.get_gallery_data(gid)
                if gallery_data and 'files' in gallery_data and len(gallery_data['files']) > 0:
                    hitomi_url = f"https://hitomi.la/reader/{gid}.html"

                    if logger:
                        logger.info(f"hdoujin 失败，回退到 hitomi gid 直接下载: gid={gid}, url={hitomi_url}, files={len(gallery_data['files'])}")

                    return hitomi_url, hitomi_tool
                else:
                    if logger:
                        logger.warning(f"Hitomi 画廊 {gid} 没有文件数据")
            except ValueError as ve:
                if logger:
                    logger.warning(f"Hitomi 画廊 {gid} 不存在: {ve}")

    except Exception as e:
        if logger:
            logger.warning(f"hitomi gid 下载失败: {e}")

    # 如果 hitomi 也失败，最后尝试 nhentai
    if category not in ['doujinshi', 'manga']:
        return None, None
    try:
        title = gmetadata.get('title') or gmetadata.get('title_jpn')
        if not title:
            return None, None

        # 使用 nhentai 工具进行搜索
        nhentai_tool = nhentai.NHentaiTools(cookie=app.config['NHENTAI_COOKIE'], logger=logger)

        # 获取原始标题和语言信息用于更精确的匹配
        original_title = gmetadata.get('title_jpn')
        language = None
        for tag in gmetadata.get('tags', []):
            if isinstance(tag, str):
                if tag.startswith('language:'):
                    lang_name = tag.split(':', 1)[1]
                    # 排除 'translated' 和 'rewrite' 标签
                    if lang_name not in ['translated', 'rewrite', 'text cleaned']:
                        language = lang_name
                        break

        nhentai_id = nhentai_tool.search_by_title(title, original_title, language)
        if logger:
            logger.info(f"hitomi 失败，回退到 nhentai 搜索: title='{title}', original_title='{original_title}', language='{language}' -> nhentai_id={nhentai_id}")

        if nhentai_id:
            if logger:
                logger.info(f"找到匹配的 nhentai 画廊 {nhentai_id}，切换到 nhentai 下载")

            nhentai_url = f'https://nhentai.net/g/{nhentai_id}/'

            return nhentai_url, nhentai_tool

    except Exception as e:
        import traceback
        if logger:
            logger.warning(f"nhentai 回退失败: {e}")
            logger.warning(f"完整错误信息: {traceback.format_exc()}")

    return None, None

def post_download_processing(dl, metadata, task_id, logger=None, tasks=None, tasks_lock=None):
    try:
        # 检查是否被取消
        check_task_cancelled(task_id, tasks, tasks_lock)

        if not dl:
            return None, None

        # 创建 ComicInfo.xml 并转换为 CBZ
        # 确保 comicinfo_metadata 在任何分支中都有定义，避免未绑定变量
        comicinfo_metadata = {}
        if metadata.get('Writer') or metadata.get('Tags'):
            # 准备一个包含所有可用字段的字典，用于格式化
            template_vars = {k.lower(): v for k, v in metadata.items()}
            template_vars['filename'] = os.path.basename(dl)
            
            def finalize_none(value):
                return "" if value is None else value
            
            jinja_env = jinja2.Environment(finalize=finalize_none)

            def render_template(template_string):
                try:
                    template = jinja_env.from_string(template_string)
                    rendered_value = template.render(template_vars)
                    # 如果渲染结果是空字符串，也当作 None 处理
                    return rendered_value if rendered_value else None
                except Exception as e:
                    (logger.warning if logger else print)(f"Jinja2 模板渲染失败: {e}")
                    # 任何渲染失败都直接返回 None
                    return None

            # 根据 comicinfo 配置生成新的 metadata
            comicinfo_metadata = {}
            comicinfo_config = app.config.get('COMICINFO', {}) or {}

            # 定义一个从 config.yaml 中的小写键到 ComicInfo.xml 驼峰键的映射
            # 只需映射多单词复合词，单个单词会通过 key.capitalize() 自动处理
            key_map = {
                'agerating': 'AgeRating',
                'languageiso': 'LanguageISO',
                'alternateseries': 'AlternateSeries',
                'alternatenumber': 'AlternateNumber',
                'storyarc': 'StoryArc',
                'storyarcnumber': 'StoryArcNumber',
                'seriesgroup': 'SeriesGroup',
                'coverartist':'CoverArtist',
                'gtin': 'GTIN',
                'number': 'Number'
            }

            for key, value_template in comicinfo_config.items():
                if isinstance(value_template, str) and value_template:
                    formatted_value = render_template(value_template)
                    # 只有当格式化后的值不是 None 时才添加
                    if formatted_value is not None:
                        # 使用映射转换键, 如果键在映射中不存在, 则默认将其首字母大写
                        camel_key = key_map.get(key, key.capitalize())
                        comicinfo_metadata[camel_key] = formatted_value
            if logger: logger.info(f"生成的 ComicInfo 元数据: {comicinfo_metadata}")

            # 用于渲染路径的变量无法接受 None 值，因此在 comicinfo_metadata 完成之后，再添加回退机制
            template_vars['author'] = metadata.get('Penciller') or metadata.get('Writer') or None
            template_vars['series'] = metadata.get('Series') or None

            # 如果标签中包含 anthology，则将作者/画师数量限制调整为2
            tags = metadata.get('Tags', '').lower()
            limit = 2 if 'anthology' in [tag.strip() for tag in tags.split(',')] else 3

            # 为路径渲染限制作者/画师数量，避免路径过长
            for key in ('penciller', 'writer'):
                value = template_vars.get(key)
                if value and isinstance(value, str) and len([item for item in value.split(',') if item.strip()]) >= limit:
                    template_vars[key] = 'anthology'

            # 基于可能已修改的 penciller 和 writer 更新 author
            template_vars['author'] = template_vars.get('penciller') or template_vars.get('writer') or None

            move_path_template = app.config.get('MOVE_PATH')
            if move_path_template:
                # 为移动路径创建一个特殊的、健壮的 Jinja2 环境
                class UnknownUndefined(jinja2.Undefined):
                    def __str__(self):
                        return 'Unknown'
                
                def finalize_for_path(value):
                    # 此函数处理值为 None 或 "" 的情况
                    return value if value else 'Unknown'

                jinja_env_for_path = jinja2.Environment(
                    undefined=UnknownUndefined, # 处理不存在的键
                    finalize=finalize_for_path     # 处理 None 或 "" 的值
                )
                
                try:
                    path_template = jinja_env_for_path.from_string(move_path_template)
                    move_file_path = path_template.render(template_vars)
                    # 关键检查：处理渲染结果为空（例如模板是""）的情况
                    if not move_file_path:
                        (logger.warning if logger else print)(f"移动路径模板渲染结果为空, 回退到默认目录")
                        move_file_path = os.path.dirname(dl)
                    else:
                        # 检查模板是否包含文件名变量
                        template_has_filename = '{{filename}}' in move_path_template
                        if template_has_filename:
                            # 如果模板包含filename，确保有扩展名
                            if not os.path.splitext(move_file_path)[1].lower() in ['.7z', '.zip', '.cbz']:
                                move_file_path += '.cbz'
                except Exception as e:
                    (logger.warning if logger else print)(f"移动路径模板渲染失败: {e}, 回退到默认目录")
                    move_file_path = os.path.dirname(dl)
            else:
                move_file_path = os.path.dirname(dl)

            if not os.path.basename(move_file_path).lower().endswith(('.7z', '.zip', '.cbz')):
                move_file_path = os.path.join(move_file_path, os.path.basename(dl))

            cbz = cbztool.write_xml_to_zip(dl, comicinfo_metadata, app=app, logger=logger)
            if cbz and is_valid_zip(cbz):
                # 移动到指定目录（komga/lanraragi，可选）
                move_file_path = os.path.splitext(move_file_path)[0] + '.cbz'
                os.makedirs(os.path.dirname(move_file_path), exist_ok=True)
                shutil.move(cbz, move_file_path)
                (logger.info if logger else print)(f"文件移动到指定目录: {move_file_path}")
                dl = move_file_path
            else:
                return None, None

        # 检查是否被取消
        check_task_cancelled(task_id, tasks, tasks_lock)

        # 触发 Komga 媒体库入库扫描
        if app.config['KOMGA_TOGGLE'] and is_valid_zip(dl):
            if app.config['KOMGA_LIBRARY_ID']:
                kmg = komga.KomgaAPI(server=app.config['KOMGA_SERVER'], username=app.config['KOMGA_USERNAME'], password=app.config['KOMGA_PASSWORD'], logger=logger)
                if app.config['KOMGA_LIBRARY_ID']:
                    kmg.scan_library(app.config['KOMGA_LIBRARY_ID'])

        return dl, comicinfo_metadata

    except Exception as e:
        if logger: logger.error(f"Post-download processing failed: {e}")
        raise e

def download_gallery_task(url, mode, task_id, logger=None, favcat=False, tasks=None, tasks_lock=None):
    if logger: logger.info(f"Task {task_id} started, downloading from: {url}, favcat: {favcat}")
    
    # 如果没有传入 tasks 和 tasks_lock，从 app.config 获取
    if tasks is None:
        tasks = app.config.get('TASKS', {})
    if tasks_lock is None:
        tasks_lock = app.config.get('TASKS_LOCK')
    
    # 检查是否被取消
    check_task_cancelled(task_id, tasks, tasks_lock)

    # 判断平台
    is_nhentai = 'nhentai.net' in url
    is_hitomi = 'hitomi.la' in url
    is_hdoujin = 'hdoujin.org' in url

    if is_nhentai:
        gallery_tool = nhentai.NHentaiTools(cookie=app.config.get('NHENTAI_COOKIE'), logger=logger)
    elif is_hitomi:
        gallery_tool = hitomi.HitomiTools(logger=logger)
    elif is_hdoujin:
        gallery_tool = hdoujin.HDoujinTools(
            session_token=app.config['HDOUJIN_SESSION_TOKEN'],
            refresh_token=app.config['HDOUJIN_REFRESH_TOKEN'],
            clearance_token=app.config['HDOUJIN_CLEARANCE_TOKEN'],
            user_agent=app.config['HDOUJIN_USER_AGENT'],
            logger=logger
        )
    else:
        gallery_tool = app.config['EH_TOOLS']

    original_url = url

    # 获取画廊元数据
    gmetadata = gallery_tool.get_gmetadata(url)

    # 检查是否需要回退到 hitomi 或 nhentai（仅在 archive 模式且 GP 不足时）
    eh_funds = app.config.get('EH_FUNDS', {})
    gp_available = eh_funds.get('GP', '0')
    credits_available = eh_funds.get('Credits', 0)

    # 解析 GP 值（去掉 'k' 后缀）
    try:
        if gp_available.endswith('k'):
            gp_value = float(gp_available[:-1])
        else:
            gp_value = float(gp_available) / 1000
    except (ValueError, TypeError):
        gp_value = 0

    # 如果 GP 不足（少于 10k）且是 archive 模式，尝试回退 hitomi -> nhentai
    if not is_nhentai and not is_hitomi and not is_hdoujin and mode == 'archive' and gp_value < 10 and gmetadata:
        if logger:
            logger.info(f"GP 不足 (当前: {gp_available})，尝试使用兜底方案下载")

        fallback_url, fallback_tool = try_fallback_download(gmetadata, logger)
        if fallback_url:
            url = fallback_url
            gallery_tool = fallback_tool

    # 在获得 gmetadata 后，触发 task.start 事件
    if app.config['NOTIFICATION'].get('enable'):
        event_data = {
            "url": original_url,
            "task_id": task_id,
            "gmetadata": gmetadata,
        }
        notify(event="task.start", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])
    
    if not gmetadata or 'gid' not in gmetadata:
        raise ValueError("Failed to retrieve valid gmetadata for the given URL.")
    
    # 获取标题
    if gmetadata.get('title_jpn'):
        title = html.unescape(gmetadata['title_jpn'])
    else:
        title = html.unescape(gmetadata['title'])
    
    # 构建文件名，确保不超过文件系统限制
    sanitized_title = sanitize_filename(title)
    gid_suffix = f" [{gmetadata['gid']}]"
    if is_hdoujin:
        ext = ".cbz"
    elif not is_nhentai and not is_hitomi:
        ext = ".zip"
    else:
        ext = ""
    filename = truncate_filename(sanitized_title, f"{gid_suffix}{ext}")

    if logger: logger.info(f"准备下载: {filename}")

    # 更新内存和数据库任务信息
    if tasks_lock:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].filename = title
    task_db.update_task(task_id, filename=filename)

    check_task_cancelled(task_id, tasks, tasks_lock)

    # 下载路径
    if is_nhentai:
        download_dir = './data/download/nhentai'
    elif is_hitomi:
        download_dir = './data/download/hitomi'
    elif is_hdoujin:
        download_dir = './data/download/hdoujin'
    else:
        download_dir = './data/download/ehentai'
    path = os.path.join(os.path.abspath(check_dirs(download_dir)), filename)

    dl = None
    # 对于非 E-Hentai 平台，直接下载
    if is_nhentai or is_hitomi or is_hdoujin or original_url != url:
        # 直接下载
        dl = gallery_tool.download_gallery(url, path, task_id, tasks, tasks_lock)
        if dl is None:
            raise ValueError("无法下载画廊，链接无效")
    else:
        # E-Hentai 下载模式选择
        eh_mode = get_eh_mode(app.config, mode)
        # exhentai 限定的画廊在一些情况下能被 e-hentai 检索，但并不能通过 e-hentai 访问，因此当 exhentai 可用时，积极替换成 exhentai 的链接。
        if app.config.get('EXH_VALID'):
            url = url.replace("e-hentai.org", "exhentai.org")
        else:
            url = url.replace("exhentai.org", "e-hentai.org")

        original_url = url
        result = app.config['EH_TOOLS'].get_download_link(url=url, mode=eh_mode)
        check_task_cancelled(task_id, tasks, tasks_lock)

        if result:
            if result[0] == 'torrent':
                dl = send_to_aria2(torrent=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
                check_task_cancelled(task_id, tasks, tasks_lock)
                if dl is None:
                    # 死种尝试 archive
                    if gp_value < 10 and gmetadata:
                        if logger:
                            logger.info(f"GP 不足 (当前: {gp_available})，尝试兜底方案下载")
                        fallback_url, fallback_tool = try_fallback_download(gmetadata, logger)
                        if fallback_url:
                            url = fallback_url
                            gallery_tool = fallback_tool

                            dl = gallery_tool.download_gallery(url, path, task_id, tasks, tasks_lock)
                    else:
                        result = app.config['EH_TOOLS'].get_download_link(url=url, mode='archive')
                        dl = send_to_aria2(url=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
            elif result[0] == 'archive':
                if app.config.get('ARIA2_TOGGLE'):
                    dl = send_to_aria2(url=result[1], dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
                else:
                    dl = app.config['EH_TOOLS']._download(url=result[1], path=path, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
        else:
            # 对于被删除的画廊，尝试多种回退方案
            if logger:
                logger.info("画廊可能已被删除，尝试多种回退方案...")

            # 方案1: 尝试从 API 中找到有效的种子链接
            torrent_path = app.config['EH_TOOLS'].get_deleted_gallery_torrent(gmetadata)
            if torrent_path:
                if logger:
                    logger.info("找到可用的种子文件，尝试下载...")
                dl = send_to_aria2(torrent=torrent_path, dir=app.config.get('ARIA2_DOWNLOAD_DIR'), out=filename, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
                check_task_cancelled(task_id, tasks, tasks_lock)
                if dl:
                    if logger:
                        logger.info("通过种子下载成功")
                else:
                    if logger:
                        logger.warning("种子下载失败，继续尝试其他方案")
            else:
                if logger:
                    logger.warning("未找到可用的种子文件")

            # 方案2: 如果种子下载失败，尝试回退 hitomi -> nhentai
            if not dl and gmetadata:
                fallback_url, fallback_tool = try_fallback_download(gmetadata, logger)
                if fallback_url:
                    url = fallback_url
                    gallery_tool = fallback_tool

                    dl = gallery_tool.download_gallery(url, path, task_id, tasks, tasks_lock)
                    if dl and logger:
                        logger.info("兜底下载成功")

            # 如果所有方案都失败，抛出错误
            if not dl:
                raise ValueError("无法获取下载链接：画廊可能已被删除且所有回退方案均失败")

    # 检查是否被取消
    check_task_cancelled(task_id, tasks, tasks_lock)

    # 处理元数据
    if metadata_extractor:
        metadata = metadata_extractor.parse_gmetadata(gmetadata, logger=logger)
    else:
        metadata = {}
    if not is_nhentai and not is_hitomi and not is_hdoujin and original_url != url:
        # 如果切换到了兜底下载，使用原始 ehentai 的 URL 作为 Web 字段
        metadata['Web'] = original_url.split('#')[0].split('?')[0]
    else:
        metadata['Web'] = url.split('#')[0].split('?')[0]

    # 统一后处理
    final_path, comicinfo_metadata = post_download_processing(dl, metadata, task_id, logger, tasks, tasks_lock)

    # 验证处理结果
    if final_path and is_valid_zip(final_path):
        
        if logger: logger.info(f"Task {task_id} completed successfully.")
        if tasks_lock:
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id].status = TaskStatus.COMPLETED
        task_db.update_task(task_id, status=TaskStatus.COMPLETED)
        
        # 发送完成通知
        if app.config['NOTIFICATION'].get('enable'):
            event_data = {
                "url": original_url,
                "task_id": task_id,
                "gmetadata": gmetadata,
                "metadata": metadata,
                }
            notify(event="task.complete", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])

        # 如果是收藏夹任务 (且不是nhentai、hitomi和hdoujin)，执行特殊流程
        if favcat is not False and not is_nhentai and not is_hitomi and not is_hdoujin:
            if logger: logger.info(f"Task {task_id} is a favorite E-Hentai gallery, triggering special process...")
            gid = gmetadata.get('gid')
            if gid:
                favorite_record = task_db.get_eh_favorite_by_gid(gid)
                if favorite_record:
                    # 检查 favcat 是否需要更新
                    favorite_favcat = favorite_record.get('favcat')
                    if favorite_favcat and str(favorite_favcat) != str(favcat):
                        if logger: logger.info(f"Favorite record found for gid {gid} with a different favcat. Updating from {favorite_favcat} to {favcat}.")
                        task_db.update_favorite_favcat(gid, str(favcat))
                else:
                    if logger: logger.info(f"No favorite record found for gid {gid}. Adding to online and local favorites.")
                    token = gmetadata.get('token')
                    if token:
                        # 只有 EHentaiTools 才有 add_to_favorites 方法
                        if app.config['EH_TOOLS'] and hasattr(app.config['EH_TOOLS'], 'add_to_favorites'):
                            if app.config['EH_TOOLS'].add_to_favorites(gid=gid, token=token, favcat=str(favcat)):
                                # 添加到线上成功后，同步到本地数据库
                                # title 存储从 ComicInfo 提取的标题（Komga 标题）
                                # downloaded 字段会在下次同步时由 trigger_undownloaded_favorites_download 标记
                                title = comicinfo_metadata.get('Title') if comicinfo_metadata else None
                                
                                fav_data = [{
                                    'url': f"https://exhentai.org/g/{gid}/{token}/",
                                    'title': title,
                                    'favcat': str(favcat)
                                }]
                                task_db.add_eh_favorites(fav_data)
                                if logger: logger.info(f"Successfully added gid {gid} as a local favorite.")
                            else:
                                if logger: logger.error(f"Failed to add gid {gid} to online favorites.")
                        else:
                            if logger: logger.warning(f"EHentaiTools not available for adding favorites")
                    else:
                        if logger: logger.warning(f"Could not get token from gmetadata for favorite task {task_id}.")
            else:
                if logger: logger.warning(f"Could not get gid from gmetadata for favorite task {task_id}.")
        return # 返回 metadata 以便装饰器或调用者处理完成通知
    else:
        error_message = "Downloaded file is not a valid zip archive."
        # 此处直接抛出异常，装饰器会捕获并发送失败通知
        raise ValueError(error_message)
    
def task_failure_processing(url, task_id, logger, tasks, tasks_lock):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_msg = str(e)
                if "cancelled by user" in error_msg:
                    if logger: logger.info(f"Task {task_id} was cancelled by user")
                    if tasks_lock:
                        with tasks_lock:
                            if task_id in tasks:
                                tasks[task_id].status = TaskStatus.CANCELLED
                    # 更新数据库状态
                    from database import task_db
                    task_db.update_task(task_id, status=TaskStatus.CANCELLED)
                else:
                    if logger: logger.error(f"Task {task_id} failed with error: {e}")
                    if tasks_lock:
                        with tasks_lock:
                            if task_id in tasks:
                                tasks[task_id].status = TaskStatus.ERROR
                                tasks[task_id].error = str(e)
                    # 更新数据库状态
                    from database import task_db
                    task_db.update_task(task_id, status=TaskStatus.ERROR, error=str(e))
                    
                    if app.config['NOTIFICATION'].get('enable'):
                        event_data = {
                            "task_id": task_id,
                            "url": url,
                            "error": str(e)
                        }
                        notify(event="task.error", data=event_data, logger=logger, notification_config=app.config['NOTIFICATION'])
                raise e
        return wrapper
    return decorator

# 确保这个路由在所有 API 路由之后定义
# 只处理 GET 请求，避免拦截 API 的 POST/PUT/DELETE 等请求
@app.route('/', defaults={'path': ''}, methods=['GET'])
@app.route('/<path:path>', methods=['GET'])
def serve_vue_app(path):
    # 在开发模式下，我们不服务静态文件，而是让 Vue CLI 自己的服务器处理
    # 在生产模式下，我们服务构建后的 index.html
    if app.debug: # 如果是调试模式 (开发环境)
        return redirect(f"http://localhost:5173/{path}") # 重定向到 Vue 开发服务器
    else: # 如果是生产模式
        static_dir = app.static_folder
        if static_dir is None:
            return "Static folder not configured on the Flask app.", 500
        # 首先尝试提供请求的路径作为静态文件（例如CSS/JS/图片等）
        requested_file = os.path.join(static_dir, path)
        if os.path.exists(requested_file) and not os.path.isdir(requested_file):
            return send_from_directory(static_dir, path)
        
        # 如果请求的不是静态文件，则提供 index.html 让 Vue Router 处理
        index_path = os.path.join(static_dir, 'index.html')
        if not os.path.exists(index_path):
            return "Vue.js application not built. Please run 'npm run build' in the webui directory.", 500
        return send_from_directory(static_dir, 'index.html')

if __name__ == '__main__':
    # 提前判断并设置调试模式，这对于防止 reloader 重复执行副作用至关重要
    is_docker = os.path.exists('/.dockerenv') or os.environ.get('DOCKER_CONTAINER', False)
    debug_mode = not is_docker
    app.debug = debug_mode

    # 在加载配置前，先执行迁移脚本
    migrate_ini_to_yaml()
    # 初始化时加载配置，确保端口号等信息在两个进程中都可用
    check_config()

    # 在配置初始化后注册 Blueprint（确保 EH_TOOLS 等依赖已准备就绪）
    # 将 global_logger、tasks、tasks_lock 和 executor 放入 app.config
    # 确保在多进程环境下所有代码访问的是同一个实例
    app.config['GLOBAL_LOGGER'] = global_logger
    app.config['TASKS'] = tasks
    app.config['TASKS_LOCK'] = tasks_lock
    app.config['EXECUTOR'] = executor
    # 将函数和类放入 app.config 供 Blueprint 使用
    app.config['GET_TASK_LOGGER'] = get_task_logger
    app.config['TASK_FAILURE_PROCESSING'] = task_failure_processing
    app.config['DOWNLOAD_GALLERY_TASK'] = download_gallery_task
    app.config['TASK_INFO_CLASS'] = TaskInfo
    app.register_blueprint(ehentai_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(hdoujin_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(komga_bp)
    app.register_blueprint(rss_bp)
    app.register_blueprint(scheduler_bp)

    
    # 仅在主工作进程中执行一次性初始化，以避免 reloader 重复执行
    if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == 'true':
        # 初始化 RSS 缓存
        config_data = load_config()
        rss_config = config_data.get('rss', {})
        cache_ttl = rss_config.get('cache_ttl', 3600)
        init_rss_cache(cache_ttl=cache_ttl)
                
        # 启动时迁移内存中的任务到数据库
        if tasks:
            global_logger.info("正在迁移内存中的任务到数据库...")
            success = task_db.migrate_memory_tasks(tasks)
            if success:
                global_logger.info("任务迁移完成")
            else:
                global_logger.error("任务迁移失败")

        # 将重启前的进行中任务标记为失败
        global_logger.info("正在检查并标记重启前的进行中任务...")
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                cursor = conn.execute('SELECT id FROM tasks WHERE status = ?', (TaskStatus.IN_PROGRESS,))
                in_progress_tasks = cursor.fetchall()
                if in_progress_tasks:
                    for task_row in in_progress_tasks:
                        task_id = task_row[0]
                        conn.execute('UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?',
                                   (TaskStatus.ERROR, '任务因应用重启而中断', datetime.now(timezone.utc).isoformat(), task_id))
                    conn.commit()
                    global_logger.info(f"已将 {len(in_progress_tasks)} 个进行中任务标记为失败")
                else:
                    global_logger.info("没有发现进行中的任务")
        except sqlite3.Error as e:
            global_logger.error(f"标记进行中任务失败时发生数据库错误: {e}")

        # 初始化并启动调度器
        init_scheduler(app)
        # 启动后立即根据当前配置更新一次任务
        update_scheduler_jobs(app)

    try:
        # 使用已经计算好的 debug_mode 来运行应用
        # 端口优先从环境变量 API_PORT 读取,默认5001
        app.run(host='0.0.0.0', port=app.config.get('PORT', 5001), debug=app.debug)
    finally:
        executor.shutdown()
        # 确保在主应用终止时关闭子进程
        stop_notification_process()

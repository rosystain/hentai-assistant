import os, configparser, re, shutil, sqlite3
import json, html
from datetime import datetime, timezone

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
from utils import check_dirs
import nfotool
from database import task_db

from providers.ehtranslator import EhTagTranslator

# 配置 Flask 以服务 Vue.js 静态文件
# 在生产环境中，Vue.js 应用会被构建到 `webui/dist` 目录
# Flask 将从这个目录提供静态文件
app = Flask(
    __name__,
    static_folder='webui/dist/assets', # Vue.js 构建后的静态文件（JS, CSS, 图片等）
    static_url_path='/assets' # 访问静态文件的 URL 前缀
)
CORS(app) # 在 Flask 应用中启用 CORS
# 设置5001端口为默认端口
app.config['port'] = 5001

config_path = './data/config.ini'  # 使用INI配置
config_parser = configparser.ConfigParser()

# 创建一个线程池用于并发处理任务
executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

tasks = {}
tasks_lock = threading.Lock()

class TaskInfo:
    def __init__(self, future, logger, log_buffer):
        self.future = future
        self.logger = logger
        self.log_buffer = log_buffer
        self.status = "进行中"  # "完成"、"取消"、"错误"
        self.error = None
        self.filename = None # 初始 filename 为 None
        self.progress = 0  # 进度百分比 0-100
        self.downloaded = 0  # 已下载字节数
        self.total_size = 0  # 总字节数
        self.speed = 0  # 下载速度 B/s
        self.cancelled = False  # 取消标志

# 日志初始化
LOG_FILE = "./data/app.log"

def json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False),
        status=status,
        mimetype="application/json"
    )

def init_global_logger():
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = RotatingFileHandler(LOG_FILE, maxBytes=2*1024*1024, backupCount=5, encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger

global_logger = init_global_logger()

def get_task_logger(task_id):
    log_buffer = StringIO()
    buffer_handler = logging.StreamHandler(log_buffer)
    formatter = logging.Formatter(f'%(asctime)s [%(levelname)s] [task:{task_id}] %(message)s')
    buffer_handler.setFormatter(formatter)

    logger = logging.getLogger(f"task_{task_id}")
    logger.setLevel(logging.INFO)
    # 避免重复添加 handler
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, 'stream', None) == log_buffer for h in logger.handlers):
        logger.addHandler(buffer_handler)
    # 添加全局日志（带 taskid 前缀）
    class TaskIdFilter(logging.Filter):
        def filter(self, record):
            record.msg = f"[task:{task_id}] {record.msg}"
            return True
    for h in global_logger.handlers:
        if not any(isinstance(f, TaskIdFilter) for f in h.filters):
            h.addFilter(TaskIdFilter())
    return logger, log_buffer

def load_config():
    config_data = {}
    if os.path.exists(config_path):
        try:
            config_parser.read(config_path, encoding='utf-8')
            # 转换INI格式到字典格式
            for section in config_parser.sections():
                config_data[section] = {}
                for key, value in config_parser[section].items():
                    # 去除首尾引号
                    if value.startswith('"') and value.endswith('"'):
                        config_data[section][key] = value[1:-1]
                    else:
                        config_data[section][key] = value
            global_logger.info("使用INI配置文件")
        except Exception as e:
            global_logger.error(f"加载INI配置失败: {e}")
            config_data = {}
    else:
        global_logger.warning("未找到配置文件，使用默认配置")
    return config_data

def check_config():
    TRUE_VALUES = {'true', 'enable', '1', 'yes', 'on'}
    config_data = load_config()

    # 通用设置
    general = config_data.get('general', {})
    app.config['download_torrent'] = str(general.get('download_torrent', 'false')).lower() in TRUE_VALUES
    app.config['keep_torrents'] = str(general.get('keep_torrents', 'false')).lower() in TRUE_VALUES
    app.config['keep_original_file'] = str(general.get('keep_original_file', 'false')).lower() in TRUE_VALUES
    app.config['tags_translation'] = str(general.get('tags_translation', 'true')).lower() in TRUE_VALUES
    app.config['prefer_japanese_title'] = str(general.get('prefer_japanese_title', 'true')).lower() in TRUE_VALUES
    app.config['remove_ads'] = str(general.get('remove_ads', 'true')).lower() in TRUE_VALUES

    # E-Hentai 设置
    ehentai_config = config_data.get('ehentai', {})
    cookie = ehentai_config.get('cookie', '')
    app.config['eh_cookie'] = {"cookie": cookie} if cookie else {"cookie": ""}

    eh = ehentai.EHentaiTools(cookie=app.config['eh_cookie'], logger=global_logger)
    hath_toggle = eh.is_valid_cookie()

    # Aria2 RPC 设置
    aria2_config = config_data.get('aria2', {})
    aria2_enable = str(aria2_config.get('enable', 'false')).lower() in TRUE_VALUES

    if aria2_enable:
        global_logger.info("开始测试 Aria2 RPC 的连接")
        app.config['aria2_server'] = str(aria2_config.get('server', '')).rstrip('/')
        app.config['aria2_token'] = str(aria2_config.get('token', ''))
        app.config['aria2_download_dir'] = str(aria2_config.get('download_dir', '')).rstrip('/') or None
        app.config['real_download_dir'] = str(aria2_config.get('mapped_dir', '')).rstrip('/') or app.config['aria2_download_dir']

        rpc = aria2.Aria2RPC(url=app.config['aria2_server'], token=app.config['aria2_token'], logger=global_logger)
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

    # Komga API 设置
    komga_config = config_data.get('komga', {})
    komga_enable = str(komga_config.get('enable', 'false')).lower() in TRUE_VALUES

    if komga_enable:
        global_logger.info("开始测试 Komga API 的连接")
        app.config['komga_server'] = str(komga_config.get('server', '')).rstrip('/')
        app.config['komga_token'] = str(komga_config.get('token', ''))
        app.config['komga_library_dir'] = str(komga_config.get('library_dir', ''))
        app.config['komga_oneshot'] = str(komga_config.get('oneshot', '_oneshot'))
        app.config['komga_library_id'] = str(komga_config.get('library_id', ''))

        kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=global_logger)
        try:
            library = kmg.get_libraries(library_id=app.config['komga_library_id'])
            if library.status_code == 200:
                global_logger.info("Komga API 连接成功")
                komga_toggle = True
            else:
                komga_toggle = False
                global_logger.error("Komga API 连接异常, 相关功能将不可用")
        except Exception as e:
            global_logger.error(f"Komga API 连接异常: {e}")
            komga_toggle = False
    else:
        global_logger.info("Komga API 功能未启用")
        komga_toggle = False

    app.config['hath_toggle'] = hath_toggle
    app.config['aria2_toggle'] = aria2_toggle
    app.config['komga_toggle'] = komga_toggle
    app.config['checking_config'] = False
    global eh_translator
    eh_translator = EhTagTranslator(enable_translation=app.config.get('tags_translation', True))

def get_eh_mode(config, mode):
    aria2 = config.get('aria2_toggle', False)
    hath = config.get('hath_toggle', False)
    download_torrent = mode in ("torrent", "1") if mode else config.get('download_torrent', True)
    if hath and not aria2:
        return "archive"
    if aria2 and download_torrent:
        if hath:
            return "both"
        else:
            return "torrent"
    elif hath:
        return "archive"
    return "both"

def send_to_aria2(url=None, torrent=None, dir=None, out=None, logger=None, task_id=None):
    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id)

    rpc = aria2.Aria2RPC(app.config['aria2_server'], app.config['aria2_token'])
    if url != None:
        result = rpc.add_uri(url, dir=dir, out=out)
        if logger: logger.info(result)
    elif torrent != None:
        result = rpc.add_torrent(torrent, dir=dir, out=out)
        if not app.config['keep_torrents'] == True:
            os.remove(torrent)
        if logger: logger.info(result)
    gid = result['result']

    # 检查任务是否被取消
    if task_id:
        check_task_cancelled(task_id)

    # 监视 aria2 的下载进度
    file = rpc.listen_status(gid, logger=logger, task_id=task_id, tasks=tasks, tasks_lock=tasks_lock)
    if file == None:
        if logger: logger.info("疑似为死种, 尝试用 Arichive 的方式下载")
        return None
    else:
        filename = os.path.basename(file)
        if filename.lower().endswith("zip"):
            local_file_path = os.path.join(app.config['aria2_download_dir'], filename)
        else:
            parent_dir = os.path.dirname(file)
            parent_name = os.path.basename(parent_dir)
            archive_name = os.path.join(app.config['aria2_download_dir'], parent_name + ".zip")
            # 打包父目录为 zip
            shutil.make_archive(
                base_name = os.path.splitext(archive_name)[0],
                format = "zip",
                root_dir = parent_dir,
                base_dir = "."
            )
            local_file_path = archive_name

    # 完成下载后, 为压缩包添加元数据
    if os.path.exists(file):
        print(f"下载完成: {local_file_path}")
        if logger: logger.info(f"下载完成: {local_file_path}")
    return local_file_path

def sanitize_filename(s: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', '_', s)

def normalize_tilde(filename: str) -> str:
    filename = re.sub(r'(?<!\s)([〜~「])', r' \1', filename)
    filename = re.sub(r'([话話])(?!\s)', r'\1 ', filename)
    return filename

def clean_name(title):
    name = re.sub(r'[\s\-_:：•·․,，。\'’?？!！~⁓～]+$', '', title)
    return name.strip()

def extract_before_chapter(filename, matched=False):
    patterns = [
        # 1 中文/阿拉伯数字
        r'(.*?)第?\s*[一二三四五六七八九十\d]+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
        # 2. 数字在前，关键字在后
        r'(.*?)\d+\s*[卷巻话話回迴編篇章册冊席期辑輯节節部]',
        # 3. 关键字在前，数字在后
        r'(.*?)[卷巻回迴編篇章册冊席期辑輯节節部]\s*[一二三四五六七八九十\d]+',
        # 4. Vol/Vol./vol/v/V + 数字
        r'(.*?)\s*(?:vol|v|#|＃)[\s\.]*\d+',
        # 5. 方括号+数字 [数字]
        r'(.*?)\[\d+\]',
        # 6. 罗马数字
        r'(.*?)([IVXLCDM]+)\b',
        # 7. 上中下前后
        r'(.*?)[\s\-—~⁓～]+[上中下前后後]',
        # 8. 纯数字
        r'(.*?)\s*\d+'
    ]

    filename = normalize_tilde(filename)
    for pat in patterns:
        m = re.search(pat, filename, re.I)
        if m:
            return clean_name(m.group(1)).strip()
    
    # 如果没有匹配任何章节模式 → 返回第一个空格前的内容
    if matched:
        filename = filename.strip()
        idx = filename.find(' ')
        if idx == -1:
            return  clean_name(filename).strip()
        return clean_name(filename[:idx]).strip()

def fill_field(comicinfo, field, tags, prefixes):
    for prefix in prefixes:
        values = []
        for t in tags:
            if t.startswith(f"{prefix}:"):
                name = t[len(prefix)+1:]
                name = eh_translator.get_translation(name, prefix)
                values.append(name)
        if values:
            comicinfo[field] = ", ".join(values)
            return

def add_tag_first(comicinfo, new_tag: str):
    new_tag = new_tag.strip().lower()
    if not new_tag:
        return
    if 'Tags' in comicinfo and comicinfo['Tags']:
        tags = [t.strip() for t in comicinfo['Tags'].split(',') if t.strip()]
        if new_tag not in tags:
            tags.insert(0, new_tag)
        comicinfo['Tags'] = ', '.join(tags)
    else:
        comicinfo['Tags'] = new_tag

def parse_eh_tags(tags):
    comicinfo = {'Genre':'Hentai', 'AgeRating':'R18+'}
    #char_list = []
    tag_list = []
    collectionlist = []
    for tag in tags:
        # 因为 komga 这样软件并不支持 EH Tag 的 namespace，照搬会显得很别扭，所以这里会像 nhentai 那样，将一些 tag 的 namespace 去除
        matchTag = re.match(r'(.+?):(.*)',tag)
        if matchTag:
            namespace = matchTag.group(1).lower()
            tag_name = matchTag.group(2).lower()
            if namespace == 'language':
                if not tag_name == 'translated':
                    language_code = langcodes.find(tag_name).language
                    if language_code:
                        comicinfo['LanguageISO'] = language_code # 转换为BCP-47
            elif namespace == 'parody':
                # 提取 parody 内容至 SeriesGroup
                if tag_name not in ['original', 'various']:
                    kanji_parody = ehentai.get_original_tag(tag_name) # 将提取到合集的 Tag 翻译为日文
                    tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(f"{namespace}:{tag_name}") #  此处保留 namespace，方便所有 parody 相关的 tag 能排序在一块
                    if not kanji_parody == None and not app.config.get('tags_translation', True):
                        comicinfo['Genre'] = comicinfo['Genre'] + ', Parody'
                        collectionlist.append(kanji_parody)
                    else:
                        collectionlist.append(tag_name)
            elif namespace in ['character']:
                tag_name = eh_translator.get_translation(tag_name, namespace)
                tag_list.append(f"{namespace}:{tag_name}") # 保留 namespace，理由同 parody
            elif namespace == 'female' or namespace == 'mixed':
                tag_name = eh_translator.get_translation(tag_name, namespace)
                tag_list.append(tag_name) # 去掉 namespace, 仅保留内容
            elif namespace == 'male': # male 与 female 存在相同的标签, 但它们在作品中表达的含义是不同的, 为了减少歧义，这里将会丢弃所有 male 相关的共同标签，但是保留 male 限定的标签
                if tag_name in ehentai.male_only_taglist():
                    tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(tag_name)
            elif namespace == 'other':
                if tag_name not in ['extraneous ads',  'already uploaded', 'missing cover', 'forbidden content', 'replaced', 'compilation', 'incomplete', 'caption']:
                    tag_name = eh_translator.get_translation(tag_name, namespace)
                    tag_list.append(tag_name)
    # 进行以下去重
    tag_list_sorted = sorted(set(tag_list), key=tag_list.index)
    # 为 webtoon 以外的漫画指定翻页顺序
    if not 'webtoon' in tag_list_sorted:
        comicinfo['Manga'] = 'YesAndRightToLeft'
    comicinfo['Tags'] = ', '.join(tag_list_sorted)
    if not collectionlist == []: comicinfo['SeriesGroup'] = ', '.join(collectionlist)
    return comicinfo

# 解析来自 E-Hentai API 的画廊信息
def parse_gmetadata(data):
    comicinfo = {}
    if 'token' in data:
        comicinfo['Web'] = (
            f"https://exhentai.org/g/{data['gid']}/{data['token']}/, "
            f"https://e-hentai.org/g/{data['gid']}/{data['token']}/"
        )
    if 'tags' in data:
        comicinfo.update(parse_eh_tags(data['tags']))
    # 把过滤的 category 添加到 Tags，主要用途在于把 doujinshi 作为标签，方便在商业作中筛选
    if data['category'].lower() not in ['manga', 'misc', 'asianporn', 'private']:
        category = eh_translator.get_translation(data['category'], 'reclass')
        if 'Genre' in comicinfo:
            comicinfo['Genre'] = comicinfo['Genre'] + ', ' + category
        else:
            comicinfo['Genre'] = category
        add_tag_first(comicinfo, category)
    # 从标题中提取作者信息
    if app.config['prefer_japanese_title'] and not data['title_jpn'] == "":
        text = html.unescape(data['title_jpn'])
    else:
        text = html.unescape(data['title'])
    comic_market = re.search(r'\(C(\d+)\)', text)
    if comic_market:
       add_tag_first(comicinfo, f"c{comic_market.group(1)}")
    if 'SeriesGroup' not in comicinfo:
        comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'], comicinfo['SeriesGroup'] = ehentai.parse_filename(text, eh_translator)
    else:
        comicinfo['Title'], comicinfo['Writer'], comicinfo['Penciller'], _ = ehentai.parse_filename(text, eh_translator)
    if comicinfo['Writer'] == None:
        tags = data.get("tags", [])
        fill_field(comicinfo, "Writer", tags, ["group", "artist"])
    if comicinfo['Penciller'] == None:
        tags = data.get("tags", [])
        fill_field(comicinfo, "Penciller", tags, ["artist", "group"])
    # 尝试提取可能的系列名称
    series_keywords = ["multi-work series", "系列作品"]
    matched = False
    if comicinfo and comicinfo.get('Tags'):
        tags_list = [tag.strip() for tag in comicinfo['Tags'].split(', ')]
        matched = any(k.lower() == t.lower() for k in series_keywords for t in tags_list)
    if comicinfo and comicinfo.get('Title'):
        comicinfo['AlternateSeries'] = extract_before_chapter(comicinfo['Title'], matched)
    return comicinfo

def check_task_cancelled(task_id):
    """检查任务是否被取消"""
    with tasks_lock:
        task = tasks.get(task_id)
        if task and task.cancelled:
            raise Exception("Task was cancelled by user")

def download_task(url, mode, task_id, logger=None):
    try:
        if logger: logger.info(f"Task {task_id} started, downloading from: {url}")

        # 检查是否被取消
        check_task_cancelled(task_id)

        eh = ehentai.EHentaiTools(cookie=app.config['eh_cookie'], logger=logger)
        gmetadata = eh.get_gmetadata(url)
        if not gmetadata or 'gid' not in gmetadata:
            raise ValueError("Failed to retrieve valid gmetadata for the given URL.")
        if 'title_jpn' in gmetadata:
            title = html.unescape(gmetadata['title_jpn'])
        else:
            title = html.unescape(gmetadata['title'])
        filename = f"{sanitize_filename(title)} [{gmetadata['gid']}].zip"
        print(f"准备下载: {filename}")

        # 更新内存中的任务信息
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].filename = title # 在获取到文件名后立即设置

        # 同时更新数据库
        task_db.update_task(task_id, filename=filename)

        # 检查是否被取消
        check_task_cancelled(task_id)

        # 根据功能启用情况设置下载模式
        eh_mode = get_eh_mode(app.config, mode)
        result = eh.archive_download(url=url, mode=eh_mode)

        # 检查是否被取消
        check_task_cancelled(task_id)

        if result:
            if result[0] == 'torrent':
                dl = send_to_aria2(torrent=result[1], dir=app.config['aria2_download_dir'], out=filename, logger=logger, task_id=task_id)
                if dl == None:
                    result = eh.archive_download(url=url, mode='archive')
            elif result[0] == 'archive':
                if not app.config['aria2_toggle']:
                    # 通过 ehentai 的 session 直接下载
                    dl = eh._download(
                        url=result[1],
                        path=os.path.join(os.path.abspath(check_dirs('./data/download/ehentai')), filename),
                        task_id=task_id,
                        tasks=tasks,
                        tasks_lock=tasks_lock
                    )
                else:
                    dl = send_to_aria2(url=result[1], dir=app.config['aria2_download_dir'], out=filename, logger=logger, task_id=task_id)

            # 检查是否被取消
            check_task_cancelled(task_id)

            if dl:
                if 'real_download_dir' in app.config:
                    ml = os.path.join(app.config['real_download_dir'], os.path.basename(dl))
                else:
                    ml = dl
                # 将 gmetadata 转换为兼容 comicinfo 的形式
                metadata = parse_gmetadata(gmetadata)
                if metadata['Writer'] or metadata['Tags']:
                    cbz = nfotool.write_xml_to_zip(dl, ml, metadata, app=app, logger=logger)

                # 检查是否被取消
                check_task_cancelled(task_id)

                # 将文件移动到 Komga 媒体库
                # 当带有 multi-work series 标签时, 将 metadata['Series'] 作为系列，否则统一使用 oneshot
                if app.config['komga_toggle']:
                    if cbz and app.config['komga_library_dir']:
                        if 'Series' in metadata:
                            series = metadata['Series']
                        else:
                            series = app.config['komga_oneshot']
                        # 导入到 Komga
                        library_path = app.config['komga_library_dir']
                        destination = os.path.join(library_path, metadata['Penciller'], series)
                        if logger: logger.info(f"开始移动: {cbz} ==> {destination}")
                        result = shutil.move(cbz, check_dirs(destination))
                        if logger: logger.info("移动完毕")
                        kmg = komga.KomgaAPI(server=app.config['komga_server'], token=app.config['komga_token'], logger=logger)
                        if app.config['komga_library_id']:
                            kmg.scan_library(app.config['komga_library_id'])

        if logger: logger.info(f"Task {task_id} completed successfully.")
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id].status = "完成"

        # 更新数据库状态
        task_db.update_task(task_id, status="完成")
    except Exception as e:
        error_msg = str(e)
        if "cancelled by user" in error_msg:
            if logger: logger.info(f"Task {task_id} was cancelled by user")
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id].status = "取消"
            # 更新数据库状态
            task_db.update_task(task_id, status="取消")
        else:
            if logger: logger.error(f"Task {task_id} failed with error: {e}")
            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id].status = "错误"
                    tasks[task_id].error = str(e)
            # 更新数据库状态
            task_db.update_task(task_id, status="错误", error=str(e))

@app.route('/api/download', methods=['GET'])
def download_url():
    url = request.args.get('url')
    mode = request.args.get('mode')
    if not url:
        return json_response({'error': 'No URL provided'}), 400
    # 两位年份+月日时分秒，使用UTC时间避免时区问题
    task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')
    logger, log_buffer = get_task_logger(task_id)
    future = executor.submit(download_task, url, mode, task_id, logger)
    with tasks_lock:
        tasks[task_id] = TaskInfo(future, logger, log_buffer)

    # 添加任务到数据库，包含URL和mode信息用于重试
    task_db.add_task(task_id, status="进行中", url=url, mode=mode)

    return json_response({'message': f"Download task for {url} started with task ID {task_id}.", 'task_id': task_id}), 202

@app.route('/api/stop_task/<task_id>', methods=['POST'])
def stop_task(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return json_response({'error': 'Task not found'}), 404

    # 设置取消标志
    task.cancelled = True

    cancelled = task.future.cancel()
    if cancelled:
        with tasks_lock:
            task.status = "取消"
        # 更新数据库状态
        task_db.update_task(task_id, status="取消")
        return json_response({'message': 'Task cancelled'})
    else:
        return json_response({'message': 'Task could not be cancelled (可能已在运行或已完成)'})

@app.route('/api/retry_task/<task_id>', methods=['POST'])
def retry_task(task_id):
    # 从数据库获取任务信息
    task_info = task_db.get_task(task_id)
    if not task_info:
        return json_response({'error': 'Task not found'}), 404

    # 检查任务状态是否为失败
    if task_info['status'] != '错误':
        return json_response({'error': 'Only failed tasks can be retried'}), 400

    # 检查是否有URL信息
    if not task_info.get('url'):
        return json_response({'error': 'Task URL information is missing, cannot retry'}), 400

    # 获取URL和mode
    url = task_info['url']
    mode = task_info.get('mode')

    # 创建新的任务ID
    new_task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')

    # 添加新任务到数据库
    task_db.add_task(new_task_id, status="进行中", url=url, mode=mode)

    # 删除原来的失败任务
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
            conn.commit()
        print(f"已从数据库删除失败任务 {task_id}")
    except sqlite3.Error as e:
        print(f"删除失败任务时发生数据库错误: {e}")

    # 从内存中删除原来的失败任务
    with tasks_lock:
        if task_id in tasks:
            # 关闭日志缓冲区
            if hasattr(tasks[task_id], 'log_buffer'):
                tasks[task_id].log_buffer.close()
            del tasks[task_id]

    # 创建新的任务执行
    logger, log_buffer = get_task_logger(new_task_id)
    future = executor.submit(download_task, url, mode, new_task_id, logger)

    # 更新内存中的任务信息
    with tasks_lock:
        tasks[new_task_id] = TaskInfo(future, logger, log_buffer)

    return json_response({'message': f'Task retry started with new ID {new_task_id}', 'task_id': new_task_id}), 202


@app.route('/api/task_log/<task_id>')
def get_task_log(task_id):
    with tasks_lock:
        task = tasks.get(task_id)
    if not task:
        return json_response({'error': 'Task not found'}), 404
    log_content = task.log_buffer.getvalue()
    return json_response({'log': log_content})

@app.route('/api/task/<task_id>')
def get_task(task_id):
    # 首先检查内存中的任务
    with tasks_lock:
        memory_task = tasks.get(task_id)
        if memory_task:
            task_data = {
                'id': task_id,
                'status': memory_task.status,
                'error': memory_task.error,
                'filename': memory_task.filename,
                'progress': memory_task.progress,
                'downloaded': memory_task.downloaded,
                'total_size': memory_task.total_size,
                'speed': memory_task.speed,
                'log': memory_task.log_buffer.getvalue()
            }
            return json_response(task_data)

    # 如果内存中没有，检查数据库
    db_task = task_db.get_task(task_id)
    if db_task:
        return json_response(db_task)

    return json_response({'error': 'Task not found'}), 404

@app.route('/api/config', methods=['GET'])
def get_config():
    config_data = load_config()

    # 添加状态信息
    config_data['status'] = {
        'hath_toggle': bool(app.config.get('hath_toggle', False)),
        'aria2_toggle': bool(app.config.get('aria2_toggle', False)),
        'komga_toggle': bool(app.config.get('komga_toggle', False)),
    }
    return json_response(config_data)

@app.route('/api/config', methods=['POST'])
def update_config():
    data = request.get_json()
    if not data:
        return json_response({'error': 'Invalid JSON data'}), 400

    # 移除状态信息
    config_data = {k: v for k, v in data.items() if k != 'status'}

    # 保存为INI格式
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            # 手动写入配置以控制格式，确保等号两侧没有空格
            section_count = 0
            for section_name, section_data in config_data.items():
                # 在非第一个section前添加空行
                if section_count > 0:
                    f.write('\n')
                f.write(f'[{section_name}]\n')
                for key, value in section_data.items():
                    # 如果值包含特殊字符，添加引号
                    if isinstance(value, str) and (' ' in value or any(c in value for c in ['#', ';', '='])):
                        f.write(f'{key}="{value}"\n')
                    else:
                        f.write(f'{key}={value}\n')
                section_count += 1
    except Exception as e:
        return json_response({'error': f'Failed to save config: {e}'}), 500

    app.config['checking_config'] = True
    executor.submit(check_config)
    return json_response({'message': 'Config updated successfully', 'status_check_started': True}), 200

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    status_filter = request.args.get('status')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))

    # 从数据库获取任务列表
    db_tasks, total = task_db.get_tasks(status_filter, page, page_size)

    # 合并内存中的活跃任务信息
    with tasks_lock:
        for db_task in db_tasks:
            task_id = db_task['id']
            if task_id in tasks:
                memory_task = tasks[task_id]
                # 用内存中的最新信息更新数据库任务
                db_task.update({
                    'status': memory_task.status,
                    'error': memory_task.error,
                    'log': memory_task.log_buffer.getvalue(),
                    'filename': memory_task.filename,
                    'progress': memory_task.progress,
                    'downloaded': memory_task.downloaded,
                    'total_size': memory_task.total_size,
                    'speed': memory_task.speed
                })

                # 同步更新数据库
                task_db.update_task(
                    task_id,
                    status=memory_task.status,
                    error=memory_task.error,
                    log=memory_task.log_buffer.getvalue(),
                    filename=memory_task.filename,
                    progress=memory_task.progress,
                    downloaded=memory_task.downloaded,
                    total_size=memory_task.total_size,
                    speed=memory_task.speed
                )

    # 按任务ID降序排序（任务ID基于时间，新的ID更大）
    db_tasks.sort(key=lambda x: x.get('id', ''), reverse=True)

    # 获取各个状态的任务数量统计
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取各个状态的总数
            all_count = sum(status_counts.values())
            in_progress_count = status_counts.get('进行中', 0)
            completed_count = status_counts.get('完成', 0)
            cancelled_count = status_counts.get('取消', 0)
            failed_count = status_counts.get('错误', 0)
    except sqlite3.Error as e:
        print(f"Database error getting status counts: {e}")
        all_count = total
        in_progress_count = 0
        completed_count = 0
        failed_count = 0

    return json_response({
        'tasks': db_tasks,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'status_counts': {
            'all': all_count,
            'in-progress': in_progress_count,
            'completed': completed_count,
            'cancelled': cancelled_count,
            'failed': failed_count
        }
    })

@app.route('/api/task_stats', methods=['GET'])
def get_task_stats():
    """获取任务统计信息"""
    try:
        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            # 获取各种状态的任务数量
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取总任务数
            cursor = conn.execute('SELECT COUNT(*) as total FROM tasks')
            total_tasks = cursor.fetchone()['total']

            # 获取进行中任务数
            in_progress = status_counts.get('进行中', 0)

            # 获取已完成任务数
            completed = status_counts.get('完成', 0)

            # 获取取消任务数
            cancelled = status_counts.get('取消', 0)

            # 获取失败任务数（只包括错误）
            failed = status_counts.get('错误', 0)

            return json_response({
                'total': total_tasks,
                'in_progress': in_progress,
                'completed': completed,
                'cancelled': cancelled,
                'failed': failed,
                'status_counts': status_counts
            })

    except sqlite3.Error as e:
        print(f"Database error getting task stats: {e}")
        return json_response({'error': 'Failed to get task statistics'}), 500

@app.route('/api/clear_tasks', methods=['POST'])
def clear_tasks():
    status_to_clear = request.args.get('status')
    if not status_to_clear:
        return json_response({'error': 'No status provided to clear'}), 400

    # 从数据库清除任务
    success = task_db.clear_tasks(status_to_clear)
    if not success:
        return json_response({'error': 'Failed to clear tasks from database'}), 500

    # 同时从内存清除对应任务
    with tasks_lock:
        tasks_to_keep = {}
        for tid, task_info in tasks.items():
            # 支持清除"失败"状态（只包括"错误"，不包括"取消"）
            if status_to_clear == "失败":
                if task_info.status == "错误":
                    # 清除日志缓冲区
                    task_info.log_buffer.close()
                else:
                    tasks_to_keep[tid] = task_info
            elif task_info.status == status_to_clear:
                # 清除日志缓冲区
                task_info.log_buffer.close()
            else:
                tasks_to_keep[tid] = task_info
        tasks.clear()
        tasks.update(tasks_to_keep)

    return json_response({'message': f'Tasks with status "{status_to_clear}" cleared successfully'}), 200

# Catch-all 路由，用于服务 Vue.js 的 index.html
# 确保这个路由在所有 API 路由之后定义
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_vue_app(path):
    # 在开发模式下，我们不服务静态文件，而是让 Vue CLI 自己的服务器处理
    # 在生产模式下，我们服务构建后的 index.html
    if app.debug: # 如果是调试模式 (开发环境)
        return redirect(f"http://localhost:5173/{path}") # 重定向到 Vue 开发服务器
    else: # 如果是生产模式
        # 确保 index.html 存在于 webui/dist 目录
        index_path = os.path.join(os.path.dirname(__file__), 'webui', 'dist', 'index.html')
        if not os.path.exists(index_path):
            return "Vue.js application not built. Please run 'npm run build' in the webui directory.", 500
        return send_from_directory(os.path.join(os.path.dirname(__file__), 'webui', 'dist'), 'index.html')

if __name__ == '__main__':
    # 检查配置文件是否存在，如果不存在则创建示例配置
    config_path = './data/config.ini'
    ini_example_path = './data/config.ini.example'

    if not os.path.exists(config_path):
        if os.path.exists(ini_example_path):
            shutil.copy(ini_example_path, config_path)
            global_logger.info("已创建INI配置文件示例，请修改 config.ini")
        else:
            global_logger.error("配置文件不存在，且未找到配置文件示例，请手动创建配置文件。")
            exit(1)
    else:
        check_config()


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
                cursor = conn.execute('SELECT id FROM tasks WHERE status = ?', ('进行中',))
                in_progress_tasks = cursor.fetchall()
                if in_progress_tasks:
                    for task_row in in_progress_tasks:
                        task_id = task_row[0]
                        conn.execute('UPDATE tasks SET status = ?, error = ?, updated_at = ? WHERE id = ?',
                                   ('错误', '任务因应用重启而中断', datetime.now(timezone.utc).isoformat(), task_id))
                    conn.commit()
                    global_logger.info(f"已将 {len(in_progress_tasks)} 个进行中任务标记为失败")
                else:
                    global_logger.info("没有发现进行中的任务")
        except sqlite3.Error as e:
            global_logger.error(f"标记进行中任务失败时发生数据库错误: {e}")

        try:
            # 在生产模式下，debug 应该设置为 False
            app.run(host='0.0.0.0', port=app.config['port'], debug=True)
        finally:
            executor.shutdown()

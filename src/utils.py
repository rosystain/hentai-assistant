import os, json, re
import zipfile
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from glob import glob

def json_output(data):
    return json.dumps(data, indent=4, ensure_ascii=False)

# 检查目录是否存在
def check_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path

# 判断是否为 URL
def is_url(text):
    # 正则表达式用于匹配 URL
    url_pattern = re.compile(r'(https?://[^\s]+)')
    return re.match(url_pattern, text) is not None


'''def map_dir(path):
    if config.komga_mapped_dir == None:
        return path
    else:
        return path.replace(config.komga_path, config.komga_mapped_dir)'''

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
    match = re.search(r'\(([^)]+)\)\s*(?:\[[^\]]+\]\s*)+$', text)
    if match:
        parody = match.group(1).strip()
    else:
        # 匹配末尾直接是 () 的情况
        match = re.search(r'\(([^)]+)\)\s*$', text)
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

def parse_filename(text, translator):
    # 去除所有括号内的内容, 将清理后的文本作为标题
    title = re.sub(r'\[.*?\]|\(.*?\)', '', text).strip()
    print(f'从文件名{text}中解析到 Title:', title)
    # 匹配第一个活动号 (Cxxx)
    match_c = re.search(r'\(C\d+\)', text)
    if match_c:
        # 活动号后的文本
        after_c = text[match_c.end():].strip()
    else:
        # 没有活动号，就从头开始
        after_c = text
    # 取最后一个括号里的内容为原作信息
    parody = extract_parody(after_c, translator)
    # 匹配开头[]内的内容,在EH的命名规范中,它总是代表作者信息
    search_author = re.search(r'\[(.+?)\]', after_c)
    if not search_author == None:
        search_writer = re.search(r'(.+?)\s*\((.+?)\)', search_author.group(1))
        # 判断作者和画师
        if not search_writer == None:
            writer = search_writer.group(1) # 同人志的情况下，把社团视为 writer
            penciller = search_writer.group(2) # 把该漫画的作者视为 penciller
        else:
            writer = penciller = search_author.group(1)
        # 有时候也会在作者信息中著名原著作者, 尝试去分离信息, 并将原著作者与社团共同视为 writer
        for s in [ '、', ',']:
            if s in penciller:
                writer = writer + ', ' + penciller.split(s)[0]
                print('\nWriter:', writer)
                penciller = penciller.split(s)[1]
                print('Penciller:', penciller)
        return title, writer, penciller, parody
    else:
        return title, None, None, parody

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

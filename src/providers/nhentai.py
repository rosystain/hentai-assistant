import cloudscraper
import re
import json
import os
import time
from utils import check_dirs

def try_n(retries):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for i in range(retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if i == retries - 1:
                        raise e
                    time.sleep(1)
        return wrapper
    return decorator

class File:
    def __init__(self, data):
        self.url = data.get('url')
        self.referer = data.get('referer')
        self.name = data.get('name')

class File_nhentai(File):
    type = 'nhentai'
    format = 'page:04;'

class Info:
    def __init__(self, host, id, id_media, title, title_jpn, p, artists, groups, series, characters, tags, lang, category, formats):
        self.host = host
        self.id = id
        self.id_media = id_media
        self.title = title
        self.title_jpn = title_jpn
        self.p = p
        self.artists = artists
        self.groups = groups
        self.series = series
        self.characters = characters
        self.tags = tags
        self.lang = lang
        self.category = category
        self.formats = formats

def format_filename(site, data, ext):
    page = data.get('page', 0)
    filename = f"{site}_{page:04d}.{ext}"
    filename = filename.replace('/', '_').replace('\\', '_')
    return filename

# nhentai域名列表，用于尝试不同的CDN域名
NHENTAI_DOMAINS = ['', '1', '2', '3', '4', '5', '6', '7', '8', '9']

def build_nhentai_image_urls(media_id, page_num, ext):
    return [f'https://i{domain_num}.nhentai.net/galleries/{media_id}/{page_num}.{ext}' for domain_num in NHENTAI_DOMAINS]

def get_id(url):
    url = url.rstrip('/')
    try:
        return int(url)
    except:
        match = re.search(r'/g/(\d+)', url)
        return int(match.group(1)) if match else None

def _parse_gallery(gal):
    host = 'https://i.nhentai.net'
    id = int(gal['id'])
    id_media = int(gal['media_id'])
    title = gal['title']['english'] or gal['title']['japanese'] or gal['title']['pretty']
    title_jpn = gal['title']['japanese'] or gal['title']['pretty']
    images = gal.get('images', {})
    pages = images.get('pages', []) if images else []
    p = len(pages)
    artists, groups, series, characters, tags = [], [], [], [], []
    lang = category = None
    tags_list = gal.get('tags') or []
    for tag in tags_list:
        tag_type = tag['type']
        if tag_type == 'artist':
            name = tag['name'].split('|')[0].strip().trim()
            artists.append(name)
        elif tag_type == 'group':
            name = tag['name'].split('|')[0].strip().trim()
            groups.append(name)
        elif tag_type == 'parody':
            series.append(tag['name'])
        elif tag_type == 'character':
            characters.append(tag['name'])
        elif tag_type == 'language':
            lang = tag['name']
        elif tag_type == 'category':
            category = tag['name']
        elif tag_type == 'tag':
            tags.append(tag['name'])
    formats = [{'j':'jpg', 'p':'png', 'g':'gif', 'w':'webp'}.get(img['t'], 'jpg') for img in pages]
    return Info(host, id, id_media, title, title_jpn, p, artists, groups, series, characters, tags, lang, category, formats)

@try_n(3)
def get_info(id, session):
    try:
        url = f'https://nhentai.net/api/gallery/{id}'
        response = session.get(url)
        response.raise_for_status()
        gal = response.json()
        return _parse_gallery(gal)
    except Exception as e:
        try:
            url = f'https://nhentai.net/g/{id}/1/'
            response = session.get(url, headers={'Referer': f'https://nhentai.net/g/{id}/'})
            response.raise_for_status()
            html = response.text
            m = re.search(r'JSON\.parse\((.*?)\);', html)
            if m:
                gal = json.loads(json.loads(m.group(1)))
            return _parse_gallery(gal)
        except:
            raise Exception("Failed to parse nhentai data")

@try_n(3)
def get_imgs(id, session):
    try:
        info = get_info(id, session)
        if not info:
            return None, []
        imgs = []
        for p in range(1, info.p + 1):
            ext = info.formats[p - 1]
            url_page = f'https://nhentai.net/g/{id}/{p}/'
            possible_urls = build_nhentai_image_urls(info.id_media, p, ext)
            url_img = possible_urls[0]
            d = {'page': p, 'possible_urls': possible_urls}
            img = File_nhentai({'url': url_img, 'referer': url_page, 'name': format_filename('nhentai', d, ext)})
            imgs.append(img)
        return info, imgs
    except Exception as e:
        return None, []

class NHentaiTools:
    def __init__(self, cookie=None, logger=None):
        self.logger = logger
        self.session = self._create_session(delay=5)
        if cookie:
            self.session.cookies.update(cookie)
        self.timeout = 60

    def _create_session(self, delay=3):
        session = cloudscraper.create_scraper(
            browser={'browser': 'chrome', 'platform': 'windows', 'desktop': True},
            delay=delay
        )
        session.headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        return session

    def _download_file(self, url, path, headers=None, task_id=None, tasks=None, tasks_lock=None):
        try:
            request_headers = dict(self.session.headers)
            if headers:
                request_headers.update(headers)

            if self.logger:
                self.logger.debug(f"开始下载: {url} ==> {path}")

            with self.session.get(url, stream=True, timeout=self.timeout, headers=request_headers) as r:
                r.raise_for_status()
                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # 只有在有任务参数时才检查任务取消状态，避免不必要的开销
                        if task_id and tasks and tasks_lock:
                            with tasks_lock:
                                task = tasks.get(task_id)
                                if task and task.cancelled:
                                    if os.path.exists(path):
                                        os.remove(path)
                                    raise Exception("Task was cancelled by user")
                        if chunk:
                            f.write(chunk)

            if self.logger:
                self.logger.info(f"下载完成: {path}")
            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"下载失败: {url} - {e}")
            return False

    def _try_backup_urls(self, primary_url, backup_urls, path, headers=None, task_id=None, tasks=None, tasks_lock=None):
        # 首先尝试主URL
        success = self._download_file(primary_url, path, headers, task_id, tasks, tasks_lock)
        if success:
            return True

        # 主URL失败，尝试备用URL
        if self.logger:
            self.logger.warning(f"主URL下载失败，尝试备用URL: {primary_url}")

        for backup_url in backup_urls:
            if backup_url == primary_url:
                continue

            if self.logger:
                self.logger.debug(f"尝试备用URL: {backup_url}")

            success = self._download_file(backup_url, path, headers, task_id, tasks, tasks_lock)
            if success:
                if self.logger:
                    self.logger.info(f"通过备用URL下载成功: {path}")
                return True
            else:
                if self.logger:
                    self.logger.warning(f"备用URL下载失败: {backup_url}")

        return False
    
    def is_valid_cookie(self):
        try:
            response = self.session.get('https://nhentai.net/favorites/', allow_redirects=True, timeout=10)
            final_url = response.url
            if 'login' in final_url:
                if self.logger: self.logger.error("无法访问 https://nhentai.net/favorites/, 种子下载功能将不可用")
                return False
            elif final_url == 'https://nhentai.net/favorites/':
                if self.logger: self.logger.info("成功访问 https://nhentai.net/favorites/, 种子下载功能可用")
                return True
        except Exception as e:
            if self.logger: self.logger.info(f"无法打开 https://nhentai.net/favorites/, 请检查网络: {e}")
            return None

    @try_n(3)
    def get_gmetadata(self, url):
        try:
            gallery_id = get_id(url)
            if not gallery_id:
                return None
            info = get_info(gallery_id, self.session)
            if not info:
                return None
            metadata = {
                'gid': gallery_id,
                'token': '',
                'title': info.title,
                'title_jpn': info.title_jpn,
                'category': info.category or 'manga',
                'tags': []
            }
            for artist in info.artists:
                metadata['tags'].append(f"artist:{artist}")
            for group in info.groups:
                metadata['tags'].append(f"group:{group}")
            for serie in info.series:
                metadata['tags'].append(f"parody:{serie}")
            for character in info.characters:
                metadata['tags'].append(f"character:{character}")
            for tag in info.tags:
                metadata['tags'].append(f"tag:{tag}")
            if info.lang:
                metadata['tags'].append(f"language:{info.lang}")
            if info.category:
                metadata['tags'].append(f"category:{info.category}")
            gmetadata = {"gmetadata": [metadata]}
            if self.logger: self.logger.info(gmetadata)
            metadata_dir = check_dirs('data/nhentai/gmetadata/')
            metadata_file = os.path.join(metadata_dir, f'{gallery_id}.json')
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump(gmetadata, f, ensure_ascii=False, indent=4)
            return metadata
        except Exception as e:
            return None

    @try_n(3)
    def download_gallery(self, url, output_dir, task_id=None, tasks=None, tasks_lock=None):
        try:
            gallery_id = get_id(url)
            if not gallery_id:
                return None
            info, imgs = get_imgs(gallery_id, self.session)
            if not info or not imgs:
                return None
            gallery_dir = output_dir
            os.makedirs(gallery_dir, exist_ok=True)
            downloaded_files = []
            total_imgs = len(imgs)
            if self.logger:
                self.logger.info(f"开始下载 nhentai 画廊 {gallery_id}，共 {total_imgs} 张图片")
            for i, img in enumerate(imgs, 1):
                if task_id and tasks and tasks_lock:
                    with tasks_lock:
                        task = tasks.get(task_id)
                        if task and task.cancelled:
                            for file_path in downloaded_files:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                            return None
                headers = {'Referer': img.referer}
                img_path = os.path.join(gallery_dir, img.name)
                # 使用统一的备用URL尝试方法
                if hasattr(img, 'possible_urls') and img.possible_urls:
                    success = self._try_backup_urls(img.url, img.possible_urls, img_path, headers, task_id, tasks, tasks_lock)
                else:
                    success = self._download_with_referer(img.url, img_path, headers, task_id, tasks, tasks_lock)

                if success:
                    downloaded_files.append(img_path)
                    if self.logger:
                        self.logger.info(f"图片 {i}/{total_imgs} 下载成功: {img.name}")
                else:
                    if self.logger:
                        self.logger.error(f"图片 {i}/{total_imgs} 所有链接下载失败: {img.name}")
                if task_id and tasks and tasks_lock:
                    with tasks_lock:
                        if task_id in tasks:
                            tasks[task_id].progress = int((i / total_imgs) * 100)
                time.sleep(0.5)
            if self.logger:
                self.logger.info(f"nhentai 画廊 {gallery_id} 下载完成，共下载 {len(downloaded_files)}/{total_imgs} 张图片")
            return gallery_dir
        except Exception as e:
            if self.logger:
                self.logger.error(f"下载 nhentai 画廊失败: {e}")
            return None

    @try_n(3)
    def _download_with_referer(self, url, path, headers=None, task_id=None, tasks=None, tasks_lock=None):
        # 检查是否为nhentai图片链接
        if 'nhentai.net' in url and '/galleries/' in url:
            return self._download_nhentai_image(url, path, headers, task_id, tasks, tasks_lock)

        # 通用下载逻辑（日志已在_download_file中统一处理）
        return self._download_file(url, path, headers, task_id, tasks, tasks_lock)

    @try_n(3)
    def _download_nhentai_image(self, url, path, headers=None, task_id=None, tasks=None, tasks_lock=None):
        # 检查URL格式是否为nhentai图片链接
        match = re.search(r'https://i(\d*)\.nhentai\.net/galleries/(\d+)/(\d+)\.(\w+)', url)
        if not match:
            # 如果不是nhentai格式的URL，直接返回False，让调用者处理
            return False

        domain_num, media_id, page_num, ext = match.groups()

        if self.logger:
            self.logger.info(f"开始下载 nhentai 图片: {page_num}.{ext} ==> {path}")

        # 获取所有可能的URL
        possible_urls = build_nhentai_image_urls(media_id, int(page_num), ext)

        # 使用统一的备用URL尝试方法
        success = self._try_backup_urls(url, possible_urls, path, headers, task_id, tasks, tasks_lock)

        if not success and self.logger:
            self.logger.error(f"所有域名下载失败: {url}")

        return success

import os
import json
import requests
import threading
from datetime import datetime, timedelta

from utils import remove_emoji

DB_URL = "https://github.com/EhTagTranslation/Database/releases/latest/download/db.text.json"
DB_PATH = "data/ehtranslator/db.text.json"
META_PATH = "data/ehtranslator/db_meta.json"
CHECK_INTERVAL_HOURS = 24  # 每 24 小时检查更新

def check_dirs(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path

class EhTagTranslator:
    def __init__(self, enable_translation=True):
        """
        enable_translation: 是否启用标签翻译
        """
        self.enable_translation = enable_translation
        self.db_path = DB_PATH
        self.meta_path = META_PATH
        self.tagsdict = {}

        if not self.enable_translation:
            print(f"[{datetime.now()}] 标签翻译已禁用，跳过数据库更新")
            return

        check_dirs(os.path.dirname(DB_PATH))
        # 启动时判断是否需要更新
        self.load_or_update_on_startup()
        # 启动后台定期检查（可选）
        self.start_periodic_check()

    def load_or_update_on_startup(self):
        if not self.enable_translation:
            return

        need_update = True
        if os.path.exists(self.meta_path):
            try:
                with open(self.meta_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    last_checked = datetime.fromisoformat(meta.get("last_checked"))
                    if datetime.now() - last_checked < timedelta(hours=CHECK_INTERVAL_HOURS):
                        need_update = False
            except:
                need_update = True

        if need_update:
            print(f"[{datetime.now()}] EhTagTranslation 数据库超过 {CHECK_INTERVAL_HOURS} 小时未更新，开始下载...")
            self.download_db()
        else:
            self.load_local_db()

    def load_local_db(self):
        if not self.enable_translation:
            return

        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    raw = json.load(f)
                    # 用 namespace 做字典，值是 tags 字典
                    self.tagsdict = {}
                    for group in raw.get("data", []):
                        namespace = group.get("namespace")
                        tags = group.get("data", {})
                        if namespace and tags:
                            self.tagsdict[namespace] = tags
                total_tags = sum(len(tags) for tags in self.tagsdict.values())
                print(f"[{datetime.now()}] 标签数据库加载完成，包含 {len(self.tagsdict)} 个命名空间，总计 {total_tags} 条标签")
            except:
                print(f"[{datetime.now()}] 本地数据库加载失败，将尝试下载")
                self.download_db()
        else:
            print(f"[{datetime.now()}] 本地数据库不存在，开始下载")
            self.download_db()

    def download_db(self):
        if not self.enable_translation:
            return

        try:
            response = requests.get(DB_URL, timeout=30)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
                with open(self.db_path, 'wb') as f:
                    f.write(response.content)
                print(f"[{datetime.now()}] EhTagTranslation 数据库已下载/更新")
                with open(self.meta_path, 'w', encoding='utf-8') as f:
                    json.dump({"last_checked": datetime.now().isoformat()}, f)
                # 加载数据库
                self.load_local_db()
            else:
                print(f"[{datetime.now()}] 下载失败, HTTP: {response.status_code}")
                self.load_local_db()
        except Exception as e:
            print(f"[{datetime.now()}] 下载 EhTagTranslation 数据库异常: {e}")
            self.load_local_db()

    def start_periodic_check(self):
        if not self.enable_translation:
            return

        def check():
            print(f"[{datetime.now()}] 后台定期检查 EhTagTranslation 数据库更新...")
            self.load_or_update_on_startup()
            threading.Timer(CHECK_INTERVAL_HOURS * 3600, check).start()

        threading.Thread(target=check, daemon=True).start()

    def get_translation(self, text, namespace=None):
        text = text.strip().lower()
        if not namespace == None:
            namespace = namespace.strip().lower()
        if not self.enable_translation:
            return text
        if namespace:
            info = self.tagsdict.get(namespace, {}).get(text)
        else:
            info = None
            for tags in self.tagsdict.values():
                if text in tags:
                    info = tags[text]
                    break
        if info:
            name = info.get("name", text)
            return remove_emoji(name)
        return text



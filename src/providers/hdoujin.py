import os
import re
import json
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from providers.hdoujin_api import (
    _get_session, books_search, books_get_detail, books_extra,
    books_read, books_download_page, books_download, tags, tags_filters,
    favorites_search, favorite_add, favorite_delete,
    login, auth_check, auth_refresh, clearance_check, _wrap_search_term,
    set_user_agent
)
from utils import check_dirs

class HDoujinTools:
    def __init__(self, session_token=None, refresh_token=None, clearance_token=None, user_agent=None, logger=None):
        self.logger = logger
        self.session_token = session_token
        self.refresh_token = refresh_token
        self.clearance_token = clearance_token
        self.user_agent = user_agent
        # 设置 User-Agent 到 API 模块
        if user_agent:
            set_user_agent(user_agent)
        self.session = _get_session()

    def get_tokens(self):
        """获取当前令牌"""
        return {
            'session_token': self.session_token,
            'refresh_token': self.refresh_token,
            'clearance_token': self.clearance_token,
            'user_agent': self.user_agent,
        }

    def is_valid_cookie(self):
        """检查认证状态"""
        try:
            if self.session_token:
                # 检查会话令牌
                auth_result = auth_check(self.session_token)
                if auth_result.get('code') == 200:
                    if self.logger:
                        self.logger.info("hdoujin 会话令牌有效")
                    return True
                else:
                    # 尝试刷新令牌
                    if self.logger:
                        self.logger.info("hdoujin 会话令牌无效，尝试刷新")
                    if self.refresh_token:
                        refresh_result = auth_refresh(self.refresh_token)
                        if refresh_result.get('code') == 201 and 'body' in refresh_result:
                            response_body = refresh_result['body']
                            # 刷新只返回新的 session_token，refresh_token 保持不变
                            if isinstance(response_body, dict):
                                new_session_token = response_body.get('session')
                                if new_session_token:
                                    self.session_token = new_session_token
                                    if self.logger:
                                        self.logger.info("hdoujin 会话令牌刷新成功")
                                    # 令牌刷新成功后立即更新配置
                                    try:
                                        from config import load_config, save_config
                                        config_data = load_config()
                                        self.update_config_tokens(config_data)
                                        save_config(config_data)
                                        if self.logger:
                                            self.logger.info("hdoujin 令牌已自动保存到配置")
                                    except Exception as config_e:
                                        if self.logger:
                                            self.logger.warning(f"保存刷新后的令牌到配置失败: {config_e}")
                                    return True
                        else:
                            if self.logger:
                                self.logger.warning("hdoujin 会话令牌刷新失败")
                    else:
                        if self.logger:
                            self.logger.warning("hdoujin 没有配置 refresh_token，无法刷新")
                    return False

            if self.clearance_token:
                # 检查clearance令牌
                clearance_result = clearance_check(self.clearance_token)
                if clearance_result.get('code') == 200:
                    if self.logger:
                        self.logger.info("hdoujin clearance令牌有效")
                    return True
                else:
                    if self.logger:
                        self.logger.warning("hdoujin clearance令牌无效")
                    return False

            # 如果都没有提供，尝试公开访问
            test_result = books_search({"q": "test", "page": 1})
            if test_result.get('code') == 200:
                if self.logger:
                    self.logger.info("hdoujin 公开访问可用")
                return True
            else:
                if self.logger:
                    self.logger.error("hdoujin 访问不可用")
                return False

        except Exception as e:
            if self.logger:
                self.logger.error(f"检查 hdoujin 认证状态时出错: {e}")
            return False

    def update_config_tokens(self, config_data):
        """更新配置中的令牌和 User-Agent"""
        try:
            # 获取当前令牌
            current_tokens = self.get_tokens()

            # 更新配置数据
            if 'hdoujin' not in config_data:
                config_data['hdoujin'] = {}

            config_data['hdoujin']['session_token'] = current_tokens.get('session_token', '')
            config_data['hdoujin']['refresh_token'] = current_tokens.get('refresh_token', '')
            config_data['hdoujin']['clearance_token'] = current_tokens.get('clearance_token', '')
            config_data['hdoujin']['user_agent'] = current_tokens.get('user_agent', '')

            if self.logger:
                self.logger.info("HDoujin 令牌和 User-Agent 已更新到配置")

            return True
        except Exception as e:
            if self.logger:
                self.logger.error(f"更新 HDoujin 配置令牌时出错: {e}")
            return False

    def search_by_title(self, title, original_title=None, language=None):
        """根据标题搜索 hdoujin 画廊"""
        try:
            # 如果有original_title，优先使用original_title作为搜索词
            search_title = original_title if original_title else title

            # 构建搜索参数
            query = re.sub(r'\[.*?\]|\(.*?\)', '', search_title).strip()
            params = {
                "s": _wrap_search_term(query),
            }

            # 添加语言过滤
            if language:
                # HDoujin 使用位掩码语言代码，2=English, 4=Japanese, 8=Chinese等
                lang_map = {
                    'english': 2,
                    'japanese': 4,
                    'chinese': 8,
                    'korean': 16,
                }
                lang_code = lang_map.get(language.lower())
                if lang_code:
                    params["lang"] = str(lang_code)

            result = books_search(params, self.session_token)

            if result.get('code') == 200 and 'body' in result:
                entries = result['body'].get('entries', [])
                if self.logger:
                    self.logger.info(f"hdoujin 搜索结果数量: {len(entries)}")

                if entries:
                    # 找到匹配的画廊
                    best_match = None
                    for item in entries:
                        try:
                            gallery_title = item.get('title', '')
                            gallery_title_jpn = item.get('subtitle', '')

                            # 检查标题匹配度 - 简化匹配逻辑
                            title_match = title.lower() in gallery_title.lower()
                            jpn_match = (original_title and original_title.lower() in gallery_title_jpn.lower())

                            if title_match or jpn_match:
                                best_match = item
                                if self.logger:
                                    self.logger.info(f"找到匹配的画廊: {item['id']}")
                                break
                        except Exception as e:
                            if self.logger:
                                self.logger.warning(f"处理 hdoujin 搜索结果项时出错: {e}, item: {item}")
                            continue

                    if best_match:
                        return best_match['id'], best_match['key']
                    else:
                        if self.logger:
                            self.logger.warning(f"未找到匹配的画廊")
                        return None, None
            else:
                if self.logger:
                    self.logger.warning(f"hdoujin 搜索失败: {result}")
                return None, None

        except Exception as e:
            if self.logger:
                self.logger.error(f"搜索 hdoujin 时出错: {e}")
            return None, None

    def get_gmetadata(self, url):
        """获取画廊元数据"""
        try:
            # 从URL解析gallery_id和gallery_key
            # hdoujin URL格式: https://hdoujin.org/g/{id}/{key}
            import re
            match = re.search(r'/g/(\d+)/([^/?]+)', url)
            if not match:
                if self.logger:
                    self.logger.error(f"无法从URL解析gallery_id和gallery_key: {url}")
                return None

            gallery_id = match.group(1)
            gallery_key = match.group(2)

            # 获取详细书籍信息
            detail_result = books_get_detail(gallery_id, gallery_key, self.session_token)
            if detail_result.get('code') != 200 or 'body' not in detail_result:
                if self.logger:
                    self.logger.error(f"获取书籍详情失败: {detail_result}")
                return None

            book_data = detail_result['body']

            # 构建元数据
            # hdoujin category: 4=doujinshi, 2=manga
            category_map = {
                4: 'Doujinshi',
                2: 'Manga'
            }
            category_num = book_data.get('category', 2)
            category_name = category_map.get(category_num, 'Manga')

            metadata = {
                'gid': gallery_id,
                'token': gallery_key,
                'title': book_data.get('title', ''),
                'title_jpn': book_data.get('subtitle', ''),
                'category': category_name,
                'thumb': book_data.get('thumbnails', {}).get('base', '') + book_data.get('thumbnails', {}).get('main', {}).get('path', ''),
                'tags': [],
            }

            # 处理标签
            tags_data = book_data.get('tags', [])
            for tag in tags_data:
                namespace = tag.get('namespace')
                name = tag.get('name', '')

                # 映射命名空间，只处理已知命名空间
                namespace_map = {
                    1: 'artist',
                    2: 'group',
                    3: 'parody',
                    5: 'character',
                    8: 'male',
                    9: 'female',
                    10: 'mixed',
                    11: 'language',
                    12: 'other'
                }

                if namespace in namespace_map:
                    namespace_name = namespace_map[namespace]
                    metadata['tags'].append(f"{namespace_name}:{name}")

            # 构建 gmetadata 字典格式 (保持与其他刮削器一致)
            gmetadata = {"gmetadata": [metadata]}

            if self.logger:
                self.logger.info(f"hdoujin 元数据解析完成: {gallery_id}")

            return metadata

        except Exception as e:
            if self.logger:
                self.logger.error(f"获取 hdoujin 元数据时出错: {e}")
            return None

    def download_gallery(self, url, path, task_id=None, tasks=None, tasks_lock=None):
        """下载画廊"""
        try:
            # 从URL解析gallery_id和gallery_key
            # hdoujin URL格式: https://hdoujin.org/g/{id}/{key}
            import re
            match = re.search(r'/g/(\d+)/([^/?]+)', url)
            if not match:
                if self.logger:
                    self.logger.error(f"无法从URL解析gallery_id和gallery_key: {url}")
                return None

            gallery_id = match.group(1)
            gallery_key = match.group(2)

            if self.logger:
                self.logger.info(f"开始下载 hdoujin 画廊 {gallery_id}")

            # 获取书籍下载链接
            clearance = self.clearance_token or ""
            download_result = books_download(gallery_id, gallery_key, "0", self.session_token, clearance)
            if download_result.get('code') != 200 or 'body' not in download_result:
                if self.logger:
                    self.logger.error(f"获取书籍下载链接失败: {download_result}")
                return None

            download_url = download_result['body']
            if isinstance(download_url, dict) and 'base' in download_url:
                download_url = download_url['base']
            elif not download_url or not isinstance(download_url, str):
                if self.logger:
                    self.logger.error(f"无效的下载链接: {download_url}")
                return None

            # 下载CBZ文件
            if self.logger:
                self.logger.info(f"开始下载CBZ文件: {download_url}")

            # 检查任务取消状态
            if task_id and tasks and tasks_lock:
                with tasks_lock:
                    task = tasks.get(task_id)
                    if task and task.cancelled:
                        return None

            # 使用session下载文件
            response = self.session.get(download_url, stream=True, timeout=60)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    # 检查任务取消状态
                    if task_id and tasks and tasks_lock:
                        with tasks_lock:
                            task = tasks.get(task_id)
                            if task and task.cancelled:
                                if self.logger:
                                    self.logger.info(f"任务 {task_id} 被用户取消，正在清理文件")
                                # 删除已下载的文件
                                if os.path.exists(path):
                                    os.remove(path)
                                return None

                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # 更新进度信息
                        if task_id and tasks and tasks_lock:
                            progress = 0
                            if total_size > 0:
                                progress = min(100, int((downloaded / total_size) * 100))

                            with tasks_lock:
                                if task_id in tasks:
                                    tasks[task_id].progress = progress
                                    tasks[task_id].downloaded = downloaded
                                    tasks[task_id].total_size = total_size
                                    # 直接下载模式无法获取实时速度，设置为0
                                    tasks[task_id].speed = 0

            if self.logger:
                self.logger.info(f"下载完成: {path}")
                self.logger.info(f"hdoujin 画廊 {gallery_id} CBZ下载完成: {path}")

            return path

        except Exception as e:
            if self.logger:
                self.logger.error(f"下载 hdoujin 画廊失败: {e}")
            return None


def refresh_and_sync_hdoujin_config(app_config, logger=None):
    """
    验证并刷新 HDoujin token，确保配置文件和 app.config 同步
    
    使用单例模式：复用现有的 HDoujinTools 实例，避免频繁创建新实例导致的状态不一致。
    
    此函数用于统一处理定时任务、启动初始化和 API 调用中的 token 刷新逻辑。
    
    Args:
        app_config: Flask app.config 对象
        logger: 日志记录器
    
    Returns:
        bool: token 是否有效
    """
    try:
        from config import load_config, save_config
        
        # 1. 从配置文件读取最新值
        config_data = load_config()
        hdoujin_config = config_data.get('hdoujin', {})
        
        # 2. 获取或创建 HDoujinTools 实例（单例模式）
        hd = app_config.get('HD_TOOLS')
        
        if hd is None or not isinstance(hd, HDoujinTools):
            # 实例不存在，创建新实例
            if logger:
                logger.info("创建新的 HDoujinTools 实例")
            hd = HDoujinTools(
                session_token=hdoujin_config.get('session_token', ''),
                refresh_token=hdoujin_config.get('refresh_token', ''),
                clearance_token=hdoujin_config.get('clearance_token', ''),
                user_agent=hdoujin_config.get('user_agent', ''),
                logger=logger
            )
            app_config['HD_TOOLS'] = hd
        else:
            # 实例存在，更新 token（避免重建实例）
            if logger:
                logger.debug("复用现有 HDoujinTools 实例并更新 token")
            hd.session_token = hdoujin_config.get('session_token', '')
            hd.refresh_token = hdoujin_config.get('refresh_token', '')
            hd.clearance_token = hdoujin_config.get('clearance_token', '')
            hd.user_agent = hdoujin_config.get('user_agent', '')
            # 更新全局 User-Agent
            if hd.user_agent:
                set_user_agent(hd.user_agent)
        
        # 3. 验证并自动刷新（内部会保存到配置文件）
        is_valid = hd.is_valid_cookie()
        
        # 4. 重新读取配置文件，确保获取刷新后的 token
        config_data = load_config()
        hdoujin_config = config_data.get('hdoujin', {})
        
        # 5. 同步最新值到实例和 app.config
        # 确保实例中的 token 与配置文件一致（可能被 is_valid_cookie 刷新）
        hd.session_token = hdoujin_config.get('session_token', '')
        hd.refresh_token = hdoujin_config.get('refresh_token', '')
        hd.clearance_token = hdoujin_config.get('clearance_token', '')
        hd.user_agent = hdoujin_config.get('user_agent', '')
        
        app_config['HDOUJIN_SESSION_TOKEN'] = hd.session_token
        app_config['HDOUJIN_REFRESH_TOKEN'] = hd.refresh_token
        app_config['HDOUJIN_CLEARANCE_TOKEN'] = hd.clearance_token
        app_config['HDOUJIN_USER_AGENT'] = hd.user_agent
        app_config['HD_TOGGLE'] = is_valid
        
        if logger:
            if is_valid:
                logger.info("HDoujin token 验证成功，配置已同步")
            else:
                logger.warning("HDoujin token 验证失败")
        
        return is_valid
        
    except Exception as e:
        if logger:
            logger.error(f"刷新并同步 HDoujin 配置时发生错误: {e}")
        return False

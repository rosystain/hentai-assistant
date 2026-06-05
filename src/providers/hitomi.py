import os
import json
import requests
import subprocess
import tempfile
import time
import re
from utils import check_dirs

class HitomiTools:
    def __init__(self, logger=None):
        self.logger = logger
        self.domain = 'gold-usergeneratedcontent.net'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def get_gallery_data(self, gallery_id):
        """获取完整的画廊元数据 - 模拟JS脚本的行为"""
        url = f"https://ltn.{self.domain}/galleries/{gallery_id}.js"
        try:
            response = self.session.get(url)
            response.raise_for_status()

            # 解析完整的galleryinfo对象 (类似JS脚本的做法)
            js_content = response.text

            # 查找 galleryinfo = 的位置
            start_pos = js_content.find('galleryinfo = ')
            if start_pos == -1:
                # 尝试其他格式
                start_pos = js_content.find('galleryinfo=')
                if start_pos == -1:
                    raise ValueError("Could not find galleryinfo in JS file")

            # 找到结束位置 (通常是分号)
            end_pos = js_content.find(';', start_pos)
            if end_pos == -1:
                end_pos = len(js_content)

            # 提取JSON部分
            json_part = js_content[start_pos:end_pos]

            # 清理字符串以便JSON解析
            json_part = json_part.replace('galleryinfo = ', '').rstrip(';')

            # 解析JSON
            data = json.loads(json_part)

            return data

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise ValueError(f"Gallery {gallery_id} not found")
            raise
        except Exception as e:
            raise ValueError(f"Failed to get gallery data: {e}")

    def get_gg_script(self):
        """获取并执行GG脚本 - 使用Node.js正确执行"""
        url = f"https://ltn.{self.domain}/gg.js?_={int(time.time()*1000)}"
        try:
            response = self.session.get(url)
            response.raise_for_status()

            gg_script = response.text

            # 创建临时Node.js脚本 - 先定义gg变量，然后执行脚本
            node_script = f"""
    var gg;
    {gg_script}
    console.log(JSON.stringify(gg));
    """

            # 使用Node.js执行脚本
            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(node_script)
                temp_file = f.name

            try:
                result = subprocess.run(['node', temp_file], capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    raise ValueError(f"Node.js execution failed: {result.stderr}")

                gg_json = result.stdout.strip()
                gg = json.loads(gg_json)

                print(f"GG object from Node.js: {gg}")

                # 检查GG对象 - 由于JSON序列化，函数会丢失，需要特殊处理
                if 'b' not in gg:
                    raise ValueError("GG object missing 'b' property")

                # 保存GG脚本以供后续使用
                self._gg_script = gg_script

                # 由于函数无法JSON序列化，我们需要创建一个包装器来调用函数
                gg_wrapper = {
                    'b': gg['b'],
                    'm': self.create_gg_function_caller('m', gg_script),
                    's': self.create_gg_function_caller('s', gg_script)
                }

                return gg_wrapper

            finally:
                os.unlink(temp_file)

        except Exception as e:
            raise ValueError(f"Failed to get GG script: {e}")

    def calculate_image_url(self, file_info, gg):
        """计算图片URL - 使用Node.js执行原始JS逻辑"""
        hash_value = file_info['hash']

        try:
            # 获取GG脚本（需要传递给这个方法）
            gg_script = getattr(self, '_gg_script', None)
            if not gg_script:
                raise ValueError("GG script not available")

            # 创建Node.js脚本来计算URL
            node_script = f"""
    var gg;
    {gg_script}
    var hash = "{hash_value}";

    // 原始JS逻辑
    var m = /([\\da-f]{{61}})([\\da-f]{{2}})([\\da-f])/.exec(hash);
    if (!m) throw new Error("Invalid hash format: " + hash);

    var g = parseInt(m[3] + m[2], 16);
    var imageId = gg.s(hash);
    var subdomain = gg.m(g) + 1;
    var url = "https://w" + subdomain + ".{self.domain}/" + gg.b + imageId + "/" + hash + ".webp";

    console.log(url);
    """

            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(node_script)
                temp_file = f.name

            try:
                result = subprocess.run(['node', temp_file], capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    raise ValueError(f"Node.js URL calculation failed: {result.stderr}")

                url = result.stdout.strip()
                return url

            finally:
                os.unlink(temp_file)

        except Exception as e:
            print(f"Error calculating URL for hash {hash_value}: {e}")
            raise

    def download_image(self, url, filename, referer):
        """下载单张图片"""
        headers = {
            'Referer': referer
        }

        for attempt in range(3):
            try:
                response = self.session.get(url, headers=headers, timeout=30)
                response.raise_for_status()

                with open(filename, 'wb') as f:
                    f.write(response.content)

                return True
            except Exception as e:
                print(f"Failed to download {filename} (attempt {attempt+1}/3): {e}")
                if attempt < 2:  # 如果不是最后一次尝试，等待一下
                    time.sleep(1)

        return False

    def create_gg_function_caller(self, func_name, gg_script):
        """创建GG函数调用器"""
        def caller(arg):
            node_script = f"""
    var gg;
    {gg_script}
    console.log(gg.{func_name}({json.dumps(arg)}));
    """

            with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False) as f:
                f.write(node_script)
                temp_file = f.name

            try:
                result = subprocess.run(['node', temp_file], capture_output=True, text=True, timeout=10)
                if result.returncode != 0:
                    raise ValueError(f"Node.js function call failed: {result.stderr}")

                return int(result.stdout.strip())
            finally:
                os.unlink(temp_file)

        return caller

    def download_gallery(self, url, output_dir, task_id=None, tasks=None, tasks_lock=None):
        """下载整个画廊"""
        try:
            # 从URL中提取gallery_id
            gallery_id = self._extract_gallery_id(url)
            if not gallery_id:
                return None

            # 获取画廊数据
            gallery_data = self.get_gallery_data(gallery_id)
            if not gallery_data:
                return None

            gallery_dir = output_dir
            os.makedirs(gallery_dir, exist_ok=True)

            # 获取GG脚本
            gg = self.get_gg_script()

            # 下载每张图片
            referer = f"https://hitomi.la/reader/{gallery_id}.html"
            downloaded_files = []
            total_imgs = len(gallery_data['files'])

            if self.logger:
                self.logger.info(f"开始下载 Hitomi 画廊 {gallery_id}，共 {total_imgs} 张图片")

            for i, file_info in enumerate(gallery_data['files'], 1):
                # 检查任务是否被取消
                if task_id and tasks and tasks_lock:
                    with tasks_lock:
                        task = tasks.get(task_id)
                        if task and task.cancelled:
                            # 清理已下载的文件
                            for file_path in downloaded_files:
                                if os.path.exists(file_path):
                                    os.remove(file_path)
                            return None

                try:
                    # 计算图片URL
                    image_url = self.calculate_image_url(file_info, gg)

                    # 生成文件名
                    ext = os.path.splitext(file_info['name'])[1] or '.webp'
                    filename = f"{i:03d}{ext}"
                    filepath = os.path.join(gallery_dir, filename)

                    if self.logger:
                        self.logger.info(f"下载图片 {i}/{total_imgs}: {filename}")

                    # 下载图片
                    if self.download_image(image_url, filepath, referer):
                        downloaded_files.append(filepath)
                    else:
                        if self.logger:
                            self.logger.error(f"图片 {i}/{total_imgs} 下载失败: {filename}")
                        # 如果下载失败，退出整个下载过程
                        if self.logger:
                            self.logger.error(f"图片下载失败，退出下载过程")
                        # 清理已下载的文件
                        for file_path in downloaded_files:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        return None

                    # 更新进度
                    if task_id and tasks and tasks_lock:
                        with tasks_lock:
                            if task_id in tasks:
                                tasks[task_id].progress = int((i / total_imgs) * 100)

                    # 添加延迟避免被限制
                    time.sleep(0.5)

                except Exception as e:
                    if self.logger:
                        self.logger.error(f"处理图片 {i} 时出错: {e}")
                    continue

            if self.logger:
                self.logger.info(f"Hitomi 画廊 {gallery_id} 下载完成，共下载 {len(downloaded_files)}/{total_imgs} 张图片")

            return gallery_dir

        except Exception as e:
            if self.logger:
                self.logger.error(f"下载 Hitomi 画廊失败: {e}")
            return None

    def _extract_gallery_id(self, url):
        """从URL中提取gallery ID"""
        # 支持多种URL格式
        patterns = [
            r'-(\d+)\.html',
            r'/reader/(\d+)',
            r'/galleries/(\d+)',
            r'/g/(\d+)',
            r'^(\d+)$'  # 直接的数字ID
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def get_gmetadata(self, url):
        """获取画廊元数据"""
        try:
            gallery_id = self._extract_gallery_id(url)
            if not gallery_id:
                return None

            # 获取完整的画廊数据
            galleryinfo = self.get_gallery_data(gallery_id)
            if not galleryinfo:
                return None

            # 使用galleryinfo中的所有可用字段
            title = galleryinfo.get('title', '')
            title_jpn = galleryinfo.get('japanese_title') or title  # 使用日文标题如果可用

            # 构建更丰富的标签列表
            tags = []
            if 'tags' in galleryinfo and galleryinfo['tags']:
                for tag_info in galleryinfo['tags']:
                    if isinstance(tag_info, dict) and 'tag' in tag_info:
                        tag_str = tag_info['tag']
                        # 添加female/male标识
                        if tag_info.get('female'):
                            tag_str = f"female:{tag_str}"
                        elif tag_info.get('male'):
                            tag_str = f"male:{tag_str}"
                        tags.append(tag_str)

            # 添加艺术家标签
            if 'artists' in galleryinfo and galleryinfo['artists']:
                for artist_info in galleryinfo['artists']:
                    if isinstance(artist_info, dict) and 'artist' in artist_info:
                        tags.append(f"artist:{artist_info['artist']}")

            # 添加团队标签
            if 'groups' in galleryinfo and galleryinfo['groups']:
                for group_info in galleryinfo['groups']:
                    if isinstance(group_info, dict) and 'group' in group_info:
                        tags.append(f"group:{group_info['group']}")

            # 添加角色标签
            if 'characters' in galleryinfo and galleryinfo['characters']:
                for char_info in galleryinfo['characters']:
                    if isinstance(char_info, dict) and 'character' in char_info:
                        tags.append(f"character:{char_info['character']}")

            # 添加原作标签
            if 'parodys' in galleryinfo and galleryinfo['parodys']:
                for parody_info in galleryinfo['parodys']:
                    if isinstance(parody_info, dict) and 'parody' in parody_info:
                        tags.append(f"parody:{parody_info['parody']}")

            # 添加语言标签
            if 'language' in galleryinfo and galleryinfo['language']:
                tags.append(f"language:{galleryinfo['language']}")

            # 构建标准的元数据格式
            metadata = {
                'gid': int(gallery_id),
                'token': '',
                'title': title,
                'title_jpn': title_jpn,
                'category': galleryinfo.get('type', 'manga'),
                'tags': tags
            }

            gmetadata = {"gmetadata": [metadata]}

            if self.logger:
                self.logger.info(f"Hitomi metadata: {json.dumps(gmetadata, ensure_ascii=False)}")

            return metadata

        except Exception as e:
            if self.logger:
                self.logger.error(f"获取 Hitomi 元数据失败: {e}")
            return None
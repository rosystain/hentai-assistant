import re, os, json
import requests
from bs4 import BeautifulSoup

from utils import check_dirs

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/85.0.4183.102 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
}

def extract_parody(text, translator):
    # 匹配末尾是 () [后缀] 的情况，提取 () 内内容
    match = re.search(r'\(([^)]+)\)\s*\[.*\]\s*$', text)
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

def get_original_tag(text):
    dictpath = check_dirs('data/ehentai/translations/')
    if os.path.isfile(dictpath + 'tags.json'):
        with open(dictpath + 'tags.json', 'r', encoding='utf-8') as rf:
            tagsdict = json.load(rf)
    else:
        tagsdict = {}
    if text in tagsdict:
        return tagsdict[text]
    else:
        print('未找到词条,搜索在线内容')
        global headers
        url = 'https://ehwiki.org/wiki/' + text.replace(' ','_')
        response = requests.get(url, headers=headers)
        searchJapanese = re.search(r'Japanese</b>:\s*(.+?)<', response.text)
        if not searchJapanese == None:
            tagsdict[text] = re.sub(' ','',searchJapanese.group(1))
            with open(check_dirs(dictpath) + 'tags.json', 'w', encoding='utf-8') as wf:
                json.dump(tagsdict, wf, ensure_ascii=False, indent=4)
            return tagsdict[text]

def male_only_taglist():
    json_path = os.path.join(check_dirs("data/ehentai/tags"), "male_only_taglist.json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)['content']
    m_list = []
    if not os.path.exists("data/ehentai/fetish_listing.html"):
        url = "https://ehwiki.org/wiki/Fetish_Listing"
        global headers
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            with open("data/ehentai/fetish_listing.html", 'w') as f:
                f.write(response.text)
    with open("data/ehentai/fetish_listing.html") as f:
        soup = BeautifulSoup(f, 'html.parser')
        # 查找所有带有 "♂" 的 <a> 标签
        for a_tag in soup.find_all('a'):
            # 检查<a>标签后是否有 ♂
            if a_tag.next_sibling and "♂" in a_tag.next_sibling:
                m_list.append(a_tag.string.strip('\u200e'))
    with open(json_path, 'w') as j:
        json.dump({"content" : m_list}, j, indent=4)
    return m_list

class EHentaiTools:
    def __init__(self, cookie, logger=None):
        self.cookie = cookie
        self.logger = logger
        self.session = requests.Session()
        # 设置全局的 headers
        global headers
        self.session.headers.update(headers)
        self.session.cookies.update(cookie)

    def _check_url(self, url, name, error_msg, success_msg, keyword=None):
        try:
            response = self.session.get(url, allow_redirects=True, timeout=10)
            final_url = response.url.lower()
            valid = True
            if 'login' in final_url or (keyword and keyword not in final_url):
                valid = False
                if self.logger:
                    self.logger.error(error_msg)
            else:
                if self.logger:
                    self.logger.info(success_msg)
            return valid
        except Exception as e:
            if self.logger:
                self.logger.warning(f"无法打开 {url}, 请检查网络: {e}")
            return False

    def is_valid_cookie(self):
        # 先检查 E-Hentai
        eh_valid = self._check_url(
            "https://e-hentai.org/home.php",
            "E-Hentai",
            "无法访问 https://e-hentai.org/home.php, Archive 下载功能将不可用",
            "成功访问 https://e-hentai.org/home.php, Archive 下载功能可用"
        )
        # 再检查 ExHentai
        exh_valid = self._check_url(
            "https://exhentai.org/uconfig.php",
            "ExHentai",
            "无法访问 https://exhentai.org/uconfig.php, ExHentai 下载可能受限",
            "成功访问 https://exhentai.org/uconfig.php, ExHentai 下载功能可用",
            keyword="uconfig"
        )

        return eh_valid, exh_valid

    # 从 E-Hentai API 获取画廊信息
    def get_gmetadata(self, url):
        API = 'https://api.e-hentai.org/api.php'
        searchUrl = re.search(r'g\/(\d+?)\/(.+?)(\/|$)', url)
        if not searchUrl == None:
            gid = searchUrl.group(1)
            gtoken = searchUrl.group(2)
            data = {
                "method": "gdata",
                "gidlist": [
                    [gid,gtoken]
                ],
                "namespace": 1
                }
            response = self.session.post(API,json=data)
            if response.status_code == 200:
                if self.logger: self.logger.info(response.json())
                with open(check_dirs('data/ehentai/gmetadata/') + '{gid}.json'.format(gid=gid), 'w+', encoding='utf-8') as wf:
                    json.dump(response.json(),wf,ensure_ascii=False,indent=4)
                return response.json()['gmetadata'][0]
        else:
            if self.logger: self.logger.error(f'解析{url}时遇到了错误')

    def _download(self, url, path, task_id=None, tasks=None, tasks_lock=None):
        eh_valid, exh_valid = self.is_valid_cookie()
        if exh_valid:
            url = url.replace("e-hentai.org", "exhentai.org")
        else:
            url = url.replace("exhentai.org", "e-hentai.org")
        try:
            with self.session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0

                with open(path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        # 检查任务是否被取消
                        if task_id and tasks and tasks_lock:
                            with tasks_lock:
                                task = tasks.get(task_id)
                                if task and task.cancelled:
                                    if self.logger:
                                        self.logger.info(f"任务 {task_id} 被用户取消")
                                    # 删除已下载的文件
                                    if os.path.exists(path):
                                        os.remove(path)
                                    raise Exception("Task was cancelled by user")

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
                print(f"下载完成: {path}")
                return path
        except Exception as e:
            if self.logger:
                self.logger.error(f"下载失败: {e}")
            return None

    def archive_download(self, url, mode):
        eh_valid, exh_valid = self.is_valid_cookie()
        if exh_valid:
            url = url.replace("e-hentai.org", "exhentai.org")
        else:
            url = url.replace("exhentai.org", "e-hentai.org")
        response = self.session.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # 先看看 Torrent 情况
            if mode == "torrent" or mode == "both": # 下载种子需要开启 aria2
                torrent_a_tag = soup.find("a", string=lambda text: text and "Torrent Download" in text,onclick=True)
                # 提取链接
                if torrent_a_tag:
                    # 可直接通过 torrent_a_tag.text 中的数字判断是否有种子
                    # 获取onclick属性中的URL
                    onclick_value = torrent_a_tag['onclick']
                    search_number = re.search(r'(\d+)', torrent_a_tag.text)
                    if not search_number == None: torrent_count = int(search_number.group(1))
                    if self.logger: self.logger.info(f"找到 {torrent_count} 个种子")
                    if torrent_count > 0:
                        # 提取URL
                        start_idx = onclick_value.find("'") + 1
                        end_idx = onclick_value.find("'", start_idx)
                        torrent_window_url = onclick_value[start_idx:end_idx]
                        torrent_list = {}
                        # 请求 torrent_list_url
                        response = self.session.get(torrent_window_url)
                        if response.status_code == 200:
                            text = response.text
                            search_outdated_text = re.search(r'(.+)<p.+Outdated Torrent', text, re.S)
                            if not search_outdated_text == None:
                                if self.logger: self.logger.info('发现 Outdated Torrent')
                                t_html = search_outdated_text.group(1)
                            else: t_html = text
                            t_soup = BeautifulSoup(t_html, 'html.parser')
                            form_list = t_soup.find_all('form', method="post")
                            torrent_list = []
                            for form in form_list:
                                for td in form.find_all('td'):
                                    a_tags_with_onclick = form.find('a', onclick=True)
                                    if a_tags_with_onclick:
                                        torrent_name = a_tags_with_onclick.text + '.torrent'
                                        torrent_link = a_tags_with_onclick['href']
                                    for span in td.find_all('span'):
                                        if 'Seeds' in td.text:
                                            seeds_count = re.search(r'(\d+)', td.text).group(1)
                                torrent_list.append({'name':torrent_name, 'link':torrent_link, 'count':int(seeds_count)})
                            max_seeds_torrent = max(torrent_list, key=lambda x: x.get('count', 0))
                            if self.logger: self.logger.info(f"共找到{len(torrent_list)}个有效种子, 本次选择, {max_seeds_torrent}")
                            # 将种子下载至本地
                            torrent = self.session.get(max_seeds_torrent['link'])
                            torrent_path = os.path.join(check_dirs('./data/ehentai/torrents'), max_seeds_torrent['name'])
                            with open(torrent_path, 'wb') as f:
                                if self.logger: self.logger.info(f"开始下载: {torrent_link} ==> {torrent_path}")
                                f.write(torrent.content)
                            # 再将种子推送到 aria2, 种子将会下载到 dir
                            return 'torrent', torrent_path
            if mode == "archive" or mode == "both":
                # 直接使用GP下载Archive
                # 获取 Archive
                if self.logger: self.logger.info('\n开始进行 Archive Download')
                archive_a_tag = soup.find("a", string="Archive Download",onclick=True)
                # 提取链接
                if archive_a_tag:
                    # 获取onclick属性中的URL
                    onclick_value = archive_a_tag['onclick']
                    # 提取URL
                    start_idx = onclick_value.find("'") + 1
                    end_idx = onclick_value.find("'", start_idx)
                    download_url = onclick_value[start_idx:end_idx]
                    if self.logger: self.logger.info(f"Archive Download Link: {download_url}")
                else:
                    if self.logger: self.logger.info("No matching element found.")
                data = {
                    "dltype":"org",
                    "dlcheck":"Download Original Archive"
                }
                try:
                    response = self.session.post(download_url, data)
                    # 保存请求页面用于调试
                    # with open('data/ehentai/download.html', 'w+', encoding='utf-8') as f: f.write(response.text)
                    a_soup = BeautifulSoup(response.text, 'html.parser')
                    # 查找所有带有 onclick 属性的 <a> 标签
                    a_tags_with_onclick = a_soup.find_all('a', onclick=True)
                    # 提取 href 属性内容
                    hrefs = [a['href'] for a in a_tags_with_onclick]
                    base_url = hrefs[0].replace("?autostart=1", "")
                    final_url = base_url + '?start=1'
                    if self.logger: self.logger.info(f"开始下载: {final_url}")
                    # 返回种子地址
                    return 'archive', final_url
                except Exception as e:
                    # 如果发生了特定类型的异常，执行这里的代码
                    if self.logger: self.logger.info(f"An error occurred: {e}")

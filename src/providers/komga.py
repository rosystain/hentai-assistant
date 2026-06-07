import requests
from urllib.parse import urlparse
import requests
import json
import time
import logging
import base64 # 新增导入 base64
from utils import is_url

class KomgaAPI:
    def __init__(self, server, username, password, logger=None):
        self.server = server
        auth_string = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        self.headers = {
            'Authorization': f'Basic {encoded_auth}',
            'accept': '*/*',
            'Content-Type': 'application/json'
        }
        session = requests.Session()
        session.headers.update(self.headers)
        self.session = session
        if logger: self.logger = logger

    def _valid_session(self):
        try:
            response = self.session.get(self.server + '/api/v1/login/set-cookie', timeout=10)
            if response.status_code == 204:
                return True
            else:
                if self.logger: self.logger.error(f"Session validation failed with status code: {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            if self.logger: self.logger.error(f"Error validating session: {e}")
            return False
    def get_libraries(self, library_id=None):
        if not library_id == None:
            return self.session.get(f'{self.server}/api/v1/libraries/{library_id}')
        else:
            return self.session.get(self.server + '/api/v1/libraries')

    def scan_library(self, library_id, deep=False):
        if deep == False:
            return self.session.post(self.server + f'/api/v1/libraries/{library_id}/scan?deep=false')
        elif deep == True:
            return self.session.post(self.server + f'/api/v1/libraries/{library_id}/scan?deep=true')
        
    def get_book(self, text):
        # 获取特定 bookId 的信息
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            text_lower = text.lower()
            if 'book' in text_lower:
                book_id = last_segment
            elif 'oneshot' in text_lower:
                # 单行本通过 api/v1/books/list 查找到具体的 bookId，再返回单本书的 Response 对象
                series_id = last_segment
                request_body = {
                    "condition": {
                        "allOf": [
                            {
                                "oneShot": { "operator": "isTrue" }
                            },
                            {
                                "seriesId": {
                                "operator": "is",
                                "value": f"{series_id}"
                            }
                            }
                        ]
                    }
                }
                list_resp = self.session.post(self.server + f'/api/v1/books/list', json=request_body)
                if list_resp.status_code == 200:
                    list_data = list_resp.json()
                    if list_data.get('content'):
                        book_id = list_data['content'][0]['id']
                        return self.session.get(self.server + f'/api/v1/books/{book_id}')
                return list_resp
            else:
                # 兜底情况，提取URL最后一段作为ID
                book_id = last_segment
        else:
            book_id = text
        return self.session.get(self.server + f'/api/v1/books/{book_id}')

    def get_series(self, text):
        if is_url(text):
            parsed_url = urlparse(text)
            last_segment = parsed_url.path.strip('/').split('/')[-1]
            if 'oneshot' or 'series' in text: series_id = last_segment
        else:
            series_id = text
        return self.session.get(self.server + f'/api/v1/series/{series_id}')

    def search_book_by_title(self, title: str):
        """
        根据标题搜索书籍
        """
        request_body = {
            "condition": {
                "allOf": [
                    {
                        "title": {
                            "operator": "contains",
                            "value": title
                        }
                    }
                ]
            }
        }
        response = self.session.post(self.server + '/api/v1/books/list', json=request_body)
        if response.status_code == 200:
            return response.json().get('content', [])
        else:
            if self.logger: self.logger.error(f"Error searching book by title '{title}': {response.status_code} - {response.text}")
            return []

    def get_latest_books(self, page: int = 0, size: int = 50):
        """
        获取最新书籍列表
        
        Args:
            page: 页码（从 0 开始）
            size: 每页数量
        
        Returns:
            API 响应的 JSON 数据，包含 content 和分页信息
        """
        try:
            response = self.session.get(
                f"{self.server}/api/v1/books/latest",
                params={"page": page, "size": size}
            )
            if response.status_code == 200:
                return response.json()
            else:
                if self.logger:
                    self.logger.error(f"Failed to get latest books (page {page}): {response.status_code} - {response.text}")
                return {}
        except Exception as e:
            if self.logger:
                self.logger.error(f"Exception while getting latest books: {e}")
            return {}


    def get_collections(self, id=None, library_id=None):
        # 未提供具体 id 的情况, 获取指定 library 的所有合集
        if id == None and not library_id == None:
            url_params = f'?library_id={library_id}?size=99999'
        elif not id == None:
            url_params = ''
        return self.session.get(self.server + f'/api/v1/collections{url_params}')
    def updata_metadata_old(self, metadata, book_data, logger=None):
        # book_id 和 book_data 均可, book_id 的情况多做一次 get_book
        if type(book_data) != "dict":
            book_data = self.get_book(book_data)
        # metadata 中也包含一些 series level 的数据,因此也要同时获取 series_data 用于合并数据
        series_id = book_data['seriesId']
        series_data = self.get_series(series_id)
        if logger:  logger.info(f"开始写入数据: {metadata}")
        series_params = {}
        # 先处理 book level 的数据
        book_params = {}
        if 'Title' in metadata:
            book_params['title'] = metadata['Title']
            book_params['titleSort'] = metadata['Title']
        if 'Web' in metadata:
            print(metadata['Web'])
            if 'anilist' in metadata['Web']: label = 'AniList'
            elif 'mangaupdates' in metadata['Web']: label = 'MangaUpdates'
            elif 'hentai' in metadata['Web']: label = 'E-Hentai'
            elif 'chaika' in metadata['Web']: label = 'Chaika Panda'
            else: label = urlparse(metadata['Web']).hostname
            link = {
                'label' : label,
                'url' : metadata['Web']
                    }
            book_params['links'] = book_data['metadata']['links']
            # 去重
            is_link_existed = False
            for l in book_params['links']:
                if l['label'] == link['label']:
                    l['url'] = link['url']
                    is_link_existed = True
                    break
            if not is_link_existed == True:
                book_params['links'].append(link)
        authors = []
        if 'Writer' in metadata:
            for w in metadata['Writer'].split(', '):
                authors.append({'name' : w, 'role' : 'writer'})
        if 'Penciller' in metadata:
            for p in metadata['Penciller'].split(', '):
                authors.append({'name' : p, 'role' : 'penciller'})
        if len(authors) > 0:
            book_params['authors'] = authors
            book_params['authorsLock'] = True
            print('authors updated')
        if 'Tags' in metadata:
            tags = []
            for t in metadata['Tags'].split(', '):
                tags.append(t.lower())
            # 对 tag 去重
            book_params['tags'] = tags
            for i in book_data['metadata']['tags']:
                if i not in tags:
                    book_params['tags'].append(i)
        # 提交 book level 的数据
        self.session.patch(self.server + f'/api/v1/books/{book_data.get("id")}/metadata', json=book_params)

        # 接着处理 series level 的数据
        if 'Series' in metadata:
            series_params['Title'] = metadata['Series']
            series_params['titleSort'] = metadata['Series']
        if 'Count' in metadata:
            if series_data['metadata']['totalBookCountLock'] == False:
                series_params['totalBookCount'] = metadata['Count']
                series_params['totalBookCountLock'] = True
                series_params['status'] = 'ENDED'
                series_params['statusLock'] = True
        if 'Genre' in metadata:
            genres = metadata['Genre'].lower().split(', ')
            mergedgenres = series_data['metadata']['genres'] + genres
            series_params['genres'] = list(set(mergedgenres))
        if 'SeriesTags' in metadata:
            tags = []
            for t in metadata['SeriesTags'].split(', '):
                tags.append(t.lower())
            series_params['tags'] = list(set(t.lower() for t in series_data['metadata']['tags'] + tags))
        if series_data['metadata']['ageRatingLock'] == False:
            if 'AgeRating' in metadata:
                if '18' in metadata['AgeRating']:
                    series_params['agerating'] = 18
                    series_params['ageRatingLock'] = True
        if 'Manga' in metadata and metadata['Manga'] == "YesAndRightToLeft":
            series_params['readingDirection'] = "RIGHT_TO_LEFT"
        self.session.patch(self.server + f'/api/v1/series/{series_data.get("id")}/metadata', json=series_params)

        # 有 collections 的情况
        if 'SeriesGroup' in metadata:
            for s in metadata['SeriesGroup'].split(', '):
                print(f'将 {s} 添加至收藏集')
                # add_to_collections(series_data['id'], collection=s)
                collections_params = {
                    "name": s,
                    "ordered": False,
                    "seriesIds": [
                        series_id
                    ]
                }
                for c in self.get_collections(library_id=series_data['libraryId']):
                    if 'collection' in c['name']: # 已经存在合集的情况
                        collections_params['seriesIds'] = collections_params['seriesIds'] + c['seriesIds']
                        self.session.patch(self.server + f'/api/v1/collections/{c.get("id")}', params=collections_params)
                        break
                    else: # 否则,新建一个合集
                        self.session.patch(self.server + f'/api/v1/collections/', params=collections_params)
                        
class EventListener:
    def __init__(self, url: str, username: str, password: str, logger=None, reconnect_delay: int = 5):
        self.url = url
        self.reconnect_delay = reconnect_delay
        self.session = requests.Session()
        self.logger = logger if logger else logging.getLogger(__name__)

        # 生成 Basic Auth 头
        auth_string = f"{username}:{password}"
        encoded_auth = base64.b64encode(auth_string.encode('utf-8')).decode('utf-8')
        self.headers = {
            'Accept': 'text/event-stream',
            'Authorization': f'Basic {encoded_auth}'
        }
        self.session.headers.update(self.headers)
        self._event_buffer = {} # 用于暂存当前事件的字段

    def listen(self): # 返回类型改为 Any 或 Iterator[Dict]
        while True:
            try:
                with self.session.get(self.url, stream=True) as response:
                    if response.status_code != 200:
                        self.logger.error(f"连接失败，状态码: {response.status_code}")
                        time.sleep(self.reconnect_delay)
                        continue

                    self._event_buffer = {} # 在每次连接成功时初始化/重置缓冲区

                    for line in response.iter_lines(decode_unicode=True):
                        if line:
                            self._process_line(line)
                        elif line == '': # 空行表示一个事件块的结束
                            if 'event' in self._event_buffer and 'data' in self._event_buffer:
                                event_type = self._event_buffer.get('event')
                                event_data = self._event_buffer.get('data')
                                event_id = self._event_buffer.get('id')

                                packaged_event = {
                                    "event_type": event_type,
                                    "data": event_data
                                }
                                if event_id:
                                    packaged_event["id"] = event_id

                                yield packaged_event # 使用 yield 返回封装好的事件
                            self._event_buffer = {} # 重置缓冲区
            except requests.exceptions.RequestException as e:
                self.logger.error(f"连接错误: {e}")
                self.logger.info(f"{self.reconnect_delay}秒后尝试重连...")
                time.sleep(self.reconnect_delay)

    def _process_line(self, line: str) -> None:
        if line.startswith(':') or not line.strip():
            return

        if line.startswith('data:'):
            data = line[len('data:'):].strip()
            try:
                self._event_buffer['data'] = json.loads(data)
            except json.JSONDecodeError:
                self._event_buffer['data'] = data # 如果不是JSON，则存储原始数据
        elif line.startswith('event:'):
            self._event_buffer['event'] = line[len('event:'):].strip()
        elif line.startswith('id:'):
            self._event_buffer['id'] = line[len('id:'):].strip()
        # else: 未知行格式直接忽略，不影响事件解析
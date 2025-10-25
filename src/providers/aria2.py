import json
import requests
import base64
import time
import sys

class Aria2RPC:
    def __init__(self, url, token, logger=None):
        self.url = url
        self.token = token
        self.headers = {'Content-Type':'application/json'}
        self.id = 0

    def _request(self, method, params=None):
        self.id += 1
        payload = {'jsonrpc':'2.0', 'id':self.id, 'method':method, 'params':[f'token:{self.token}']}
        if params: payload['params'].extend(params)
        #print(params)
        response = requests.post(self.url, headers=self.headers, data = json.dumps(payload), timeout=60)
        return response.json()

    def add_uri(self, uri, dir=None, out=None):
        data = {}
        if dir != None: data['dir'] = dir
        if out != None: data['out'] = out
        return self._request('aria2.addUri', [[uri], data])

    def add_torrent(self, torrent, dir=None, out=None):
        # 读取 .torrent 文件并进行 base64 编码
        with open(torrent, 'rb') as torrent_file:
            torrent_data = torrent_file.read()
            torrent_base64 = base64.b64encode(torrent_data).decode('utf-8')
        data = {}
        if dir != None: data['dir'] = dir
        if out != None: data['out'] = out
        return self._request('aria2.addTorrent', [torrent_base64, [], data])

    def tell_active(self):
        return self._request('aria2.tellActive')

    def tell_waiting(self):
        return self._request('aria2.tellWaiting', [0,1000] )

    def tell_status(self, gid):
        return self._request('aria2.tellStatus', [gid])

    def pause(self, gid):
        return self._request('aria2.pause', [gid])

    def unpause(self, gid):
        return self._request('aria2.unpause', [gid])

    def remove(self, gid):
        return self._request('aria2.remove', [gid])

    def get_global_stat(self):
        return self._request('aria2.getGlobalStat')

    def get_version(self):
        return self._request('aria2.getVersion')

    def listen_status(self, gid, logger=None, task_id=None, tasks=None, tasks_lock=None):
        elapsed_time = 0
        elapsed_time_2 = 0

        while True:
            # 检查任务是否被取消
            if task_id and tasks and tasks_lock:
                with tasks_lock:
                    task = tasks.get(task_id)
                    if task and task.cancelled:
                        if logger:
                            logger.info(f"任务 {task_id} 被用户取消，正在停止 aria2 下载")
                        try:
                            self.remove(gid)
                        except Exception as e:
                            if logger:
                                logger.warning(f"停止 aria2 下载失败: {e}")
                        return None

            result = self.tell_status(gid)
            status = result['result']['status']
            
            # 如果下载文件已经存在, 且未在 Aria2 开启 --allow-overwrite, 则会报错并返回 errorCode 13, 此时直接返回文件路径
            if status == 'error' and result['result']['errorCode'] == "13":
                if logger:
                    logger.info("文件已存在，下载任务将被跳过")
                return result['result']['files'][0]['path']
            
            completelen = int(result['result']['completedLength'])
            totallen = int(result['result']['totalLength'])
            download_speed = int(result['result']['downloadSpeed'])

            # 计算进度百分比
            progress = 0
            if totallen > 0:
                progress = min(100, int((completelen / totallen) * 100))

            # 更新任务进度信息
            if task_id and tasks and tasks_lock:
                with tasks_lock:
                    if task_id in tasks:
                        tasks[task_id].progress = progress
                        tasks[task_id].downloaded = completelen
                        tasks[task_id].total_size = totallen
                        tasks[task_id].speed = download_speed

            # 写入日志
            if logger:
                logger.info(f"Status: {status}, Progress: {progress}%, Downloaded: {completelen}/{totallen} B, Speed: {download_speed} B/s")

            # 文件已完成长度达到总长度
            if completelen >= totallen and totallen > 0:
                if logger:
                    logger.info("文件已下载完成，等待最多 5 秒确认 status 完成")
                wait_sec = 0
                while status != 'complete' and wait_sec < 5:
                    time.sleep(1)
                    wait_sec += 1
                    result = self.tell_status(gid)
                    status = result['result']['status']
                if status != 'complete' and logger:
                    logger.info("status 仍未更新为 complete，但已视为完成")
                return result['result']['files'][0]['path']

            if completelen == 0:
                elapsed_time += 5
                if elapsed_time >= 300:
                    if logger:
                        logger.warning("No progress for 5 minutes, removing task.")
                    self.remove(gid)
                    return None

            if download_speed == 0:
                elapsed_time_2 += 5
                if elapsed_time_2 >= 7200:
                    if logger:
                        logger.warning("No speed for 2 hours, removing task.")
                    self.remove(gid)
                    return None

            if status == 'complete':
                if logger:
                    logger.info("Download complete.")
                time.sleep(5)
                return result['result']['files'][0]['path']
            else:
                time.sleep(5)

            if status in ['removed', 'error']:
                if logger:
                    logger.info("Download cancelled.")
                return None

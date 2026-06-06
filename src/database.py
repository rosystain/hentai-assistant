import sqlite3
import threading
import os
import json
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

from utils import TaskStatus, parse_gallery_url, check_dirs

class TaskDatabase:
    STATUS_MAP = {
        "in-progress": TaskStatus.IN_PROGRESS,
        "completed": TaskStatus.COMPLETED,
        "cancelled": TaskStatus.CANCELLED,
        "failed": TaskStatus.ERROR,
    }

    def __init__(self, db_path: str = './data/tasks.db'):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._latest_added_cache = None  # 缓存最新的收藏时间
        
        # 确保数据库文件的父目录存在
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            check_dirs(db_dir)
        
        self._init_database()

    def _get_conn(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path, timeout=10, check_same_thread=False)

    def _init_database(self):
        """初始化数据库表"""
        with self._get_conn() as conn:
            # 先创建表（如果不存在）
            conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    error TEXT,
                    log TEXT,
                    filename TEXT,
                    progress INTEGER DEFAULT 0,
                    downloaded INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    speed INTEGER DEFAULT 0,
                    url TEXT,
                    mode TEXT,
                    metadata TEXT,
                    comicinfo TEXT,
                    output_path TEXT,
                    target_path TEXT,
                    pending_changes TEXT,
                    repack_status TEXT,
                    move_status TEXT,
                    last_error TEXT,
                    cover_url TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 创建 global 表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS global (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # 检查 tasks 表的字段
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            # 字段重命名迁移：将 metadata_raw 改为 metadata，将 metadata_final 改为 comicinfo
            try:
                if 'metadata_raw' in columns and 'metadata' not in columns:
                    conn.execute("ALTER TABLE tasks RENAME COLUMN metadata_raw TO metadata")
                    columns.remove('metadata_raw')
                    columns.append('metadata')
                if 'metadata_final' in columns and 'comicinfo' not in columns:
                    conn.execute("ALTER TABLE tasks RENAME COLUMN metadata_final TO comicinfo")
                    columns.remove('metadata_final')
                    columns.append('comicinfo')
            except sqlite3.Error as e:
                import logging
                logging.error(f"Error renaming metadata columns: {e}")

            # 如果表已存在但缺少新字段，添加它们
            for col in (
                "url",
                "mode",
                "favcat",
                "normalized_url",
                "metadata",
                "comicinfo",
                "output_path",
                "target_path",
                "pending_changes",
                "repack_status",
                "move_status",
                "last_error",
                "cover_url"
            ):
                if col not in columns:
                    conn.execute(f'ALTER TABLE tasks ADD COLUMN {col} TEXT')

            # 为 normalized_url 创建索引（如果不存在）
            try:
                conn.execute('CREATE INDEX IF NOT EXISTS idx_tasks_normalized_url ON tasks(normalized_url)')
            except sqlite3.Error:
                pass  # 索引可能已存在

            # 为历史数据填充 normalized_url
            cursor = conn.execute('SELECT id, url FROM tasks WHERE url IS NOT NULL AND normalized_url IS NULL')
            tasks_to_update = cursor.fetchall()
            for task_id, url in tasks_to_update:
                try:
                    normalized_url, _ = self.normalize_url(url)
                    conn.execute('UPDATE tasks SET normalized_url = ? WHERE id = ?', (normalized_url, task_id))
                except Exception:
                    pass  # 跳过无法规范化的 URL

            # 迁移旧的封面 URL 到本地路由
            try:
                cursor = conn.execute("SELECT id, cover_url FROM tasks WHERE cover_url LIKE 'http%'")
                rows = cursor.fetchall()
                if rows:
                    for task_id, cover_url in rows:
                        import os
                        ext = ".jpg"
                        if cover_url and cover_url.lower().endswith(('.png', '.webp', '.jpeg', '.gif', '.jpg')):
                            ext = os.path.splitext(cover_url.split('?')[0])[1].lower()
                        new_cover_url = f"/api/covers/{task_id}{ext}"
                        conn.execute("UPDATE tasks SET cover_url = ? WHERE id = ?", (new_cover_url, task_id))
                    import logging
                    logging.info(f"Migrated {len(rows)} old cover URLs to local routes.")
            except Exception as e:
                import logging
                logging.error(f"Error migrating cover URLs: {e}")

            conn.commit()

            # 创建 eh_favorites 表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS eh_favorites (
                    gid INTEGER PRIMARY KEY,
                    token TEXT NOT NULL,
                    title TEXT,
                    originaltitle TEXT,
                    favcat INTEGER,
                    downloaded BOOLEAN DEFAULT 0,
                    komga TEXT,
                    added TEXT
                )
            ''')

            # 检查 eh_favorites 表的字段
            cursor = conn.execute("PRAGMA table_info(eh_favorites)")
            columns = [row[1] for row in cursor.fetchall()]

            # 如果表已存在但缺少新字段，添加它们
            if 'added' not in columns:
                conn.execute('ALTER TABLE eh_favorites ADD COLUMN added TEXT')
            if 'originaltitle' not in columns:
                conn.execute('ALTER TABLE eh_favorites ADD COLUMN originaltitle TEXT')

            conn.commit()

            # 创建 H@H 状态记录表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS hath_status (
                    client_id INTEGER PRIMARY KEY,
                    client TEXT NOT NULL,
                    status TEXT,
                    last_status TEXT,
                    created TEXT,
                    last_seen TEXT,
                    files_served INTEGER,
                    client_ip TEXT,
                    port INTEGER,
                    version TEXT,
                    max_speed TEXT,
                    trust TEXT,
                    quality INTEGER,
                    hitrate TEXT,
                    hathrate TEXT,
                    country TEXT,
                    last_check TEXT,
                    status_changed_at TEXT
                )
            ''')

            conn.commit()

            # 创建 Komga URL 索引表
            conn.execute('''
                CREATE TABLE IF NOT EXISTS komga_url_index (
                    normalized_url TEXT PRIMARY KEY,
                    book_id TEXT NOT NULL,
                    original_url TEXT,
                    site_type TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            conn.commit()

    def add_task(self, task_id: str, status: str = TaskStatus.IN_PROGRESS,
                 filename: Optional[str] = None, error: Optional[str] = None,
                 url: Optional[str] = None, mode: Optional[str] = None, favcat: Optional[str] = None,
                 metadata: Optional[Dict] = None, comicinfo: Optional[Dict] = None,
                 output_path: Optional[str] = None, target_path: Optional[str] = None,
                 pending_changes: Optional[Dict] = None, repack_status: Optional[str] = None,
                 move_status: Optional[str] = None, last_error: Optional[str] = None,
                 cover_url: Optional[str] = None) -> bool:
        """添加新任务"""
        status = self.STATUS_MAP.get(status, status)
        # 计算 normalized_url
        normalized_url = None
        if url:
            try:
                normalized_url, _ = self.normalize_url(url)
            except Exception:
                pass  # 如果无法规范化，保持为 None
        
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    conn.execute('''
                        INSERT OR REPLACE INTO tasks
                        (id, status, filename, error, url, mode, favcat, normalized_url,
                         metadata, comicinfo, output_path, target_path,
                         pending_changes, repack_status, move_status, last_error, cover_url,
                         created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        task_id,
                        status,
                        filename,
                        error,
                        url,
                        mode,
                        favcat,
                        normalized_url,
                        self._serialize_json(metadata),
                        self._serialize_json(comicinfo),
                        output_path,
                        target_path,
                        self._serialize_json(pending_changes),
                        repack_status,
                        move_status,
                        last_error,
                        cover_url,
                        now,
                        now
                    ))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error adding task: {e}")
                return False

    def update_task(self, task_id: str, status: Optional[str] = None, error: Optional[str] = None,
                    log: Optional[str] = None, filename: Optional[str] = None, progress: Optional[int] = None,
                    downloaded: Optional[int] = None, total_size: Optional[int] = None, speed: Optional[int] = None,
                    url: Optional[str] = None, mode: Optional[str] = None, favcat: Optional[str] = None,
                    metadata: Optional[Dict] = None, comicinfo: Optional[Dict] = None,
                    output_path: Optional[str] = None, target_path: Optional[str] = None,
                    pending_changes: Optional[Dict] = None, repack_status: Optional[str] = None,
                    move_status: Optional[str] = None, last_error: Optional[str] = None,
                    cover_url: Optional[str] = None) -> bool:
        """更新任务信息"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    updates = []
                    params = []

                    if status is not None:
                        updates.append("status = ?")
                        params.append(self.STATUS_MAP.get(status, status))
                    if error is not None:
                        updates.append("error = ?")
                        params.append(error)
                    if log is not None:
                        updates.append("log = ?")
                        params.append(log)
                    if filename is not None:
                        updates.append("filename = ?")
                        params.append(filename)
                    if progress is not None:
                        updates.append("progress = ?")
                        params.append(progress)
                    if downloaded is not None:
                        updates.append("downloaded = ?")
                        params.append(downloaded)
                    if total_size is not None:
                        updates.append("total_size = ?")
                        params.append(total_size)
                    if speed is not None:
                        updates.append("speed = ?")
                        params.append(speed)
                    if url is not None:
                        updates.append("url = ?")
                        params.append(url)
                    if mode is not None:
                        updates.append("mode = ?")
                        params.append(mode)
                    if favcat is not None:
                        updates.append("favcat = ?")
                        params.append(favcat)
                    if metadata is not None:
                        updates.append("metadata = ?")
                        params.append(self._serialize_json(metadata))
                    if comicinfo is not None:
                        updates.append("comicinfo = ?")
                        params.append(self._serialize_json(comicinfo))
                    if output_path is not None:
                        updates.append("output_path = ?")
                        params.append(output_path)
                    if target_path is not None:
                        updates.append("target_path = ?")
                        params.append(target_path)
                    if pending_changes is not None:
                        updates.append("pending_changes = ?")
                        params.append(self._serialize_json(pending_changes))
                    if repack_status is not None:
                        updates.append("repack_status = ?")
                        params.append(repack_status)
                    if move_status is not None:
                        updates.append("move_status = ?")
                        params.append(move_status)
                    if last_error is not None:
                        updates.append("last_error = ?")
                        params.append(last_error)
                    if cover_url is not None:
                        updates.append("cover_url = ?")
                        params.append(cover_url)

                    if updates:
                        updates.append("updated_at = ?")
                        params.append(datetime.now(timezone.utc).isoformat())
                        params.append(task_id)

                        query = f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?"
                        conn.execute(query, params)
                        conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error updating task: {e}")
                return False

    def get_task(self, task_id: str) -> Optional[Dict]:
        """获取单个任务"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
                    row = cursor.fetchone()
                    return self._deserialize_task(dict(row)) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting task: {e}")
                return None

    def get_task_by_normalized_url(self, normalized_url: str) -> Optional[Dict]:
        """
        根据规范化 URL 获取任务
        优先返回进行中或已完成的任务，其次是失败或取消的任务
        """
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    # 优先查询进行中或已完成的任务
                    cursor = conn.execute('''
                        SELECT * FROM tasks 
                        WHERE normalized_url = ? 
                        ORDER BY 
                            CASE status
                                WHEN ? THEN 1  -- 进行中优先级最高
                                WHEN ? THEN 2  -- 已完成次之
                                WHEN ? THEN 3  -- 取消
                                WHEN ? THEN 4  -- 失败
                                ELSE 5
                            END,
                            created_at DESC
                        LIMIT 1
                    ''', (normalized_url, TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED, 
                          TaskStatus.CANCELLED, TaskStatus.ERROR))
                    row = cursor.fetchone()
                    return self._deserialize_task(dict(row)) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting task by normalized URL: {e}")
                return None

    def get_tasks(self, status_filter: Optional[str] = None, search_query: Optional[str] = None, page: int = 1,
                  page_size: int = 20, order_by: str = "created_at DESC") -> Tuple[List[Dict], int]:
        """获取任务列表，支持分页和状态过滤"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row

                    where_clauses = []
                    params = []

                    if status_filter:
                        status_cn = self.STATUS_MAP.get(status_filter, status_filter)
                        where_clauses.append("status = ?")
                        params.append(status_cn)
                        
                    if search_query:
                        where_clauses.append("(id LIKE ? OR filename LIKE ? OR url LIKE ?)")
                        search_term = f"%{search_query}%"
                        params.extend([search_term, search_term, search_term])
                        
                    where_clause = ""
                    if where_clauses:
                        where_clause = "WHERE " + " AND ".join(where_clauses)

                    # 获取总数
                    count_query = f"SELECT COUNT(*) FROM tasks {where_clause}"
                    cursor = conn.execute(count_query, params)
                    total = cursor.fetchone()[0]

                    # 获取分页数据
                    offset = (page - 1) * page_size
                    data_query = f"""
                        SELECT * FROM tasks {where_clause}
                        ORDER BY {order_by}
                        LIMIT ? OFFSET ?
                    """
                    params.extend([page_size, offset])

                    cursor = conn.execute(data_query, params)
                    tasks = [self._deserialize_task(dict(row)) for row in cursor.fetchall()]

                    return tasks, total
            except sqlite3.Error as e:
                print(f"Database error getting tasks: {e}")
                return [], 0

    def clear_tasks(self, status: str) -> bool:
        """清除指定状态的任务"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    if status == 'all_except_in_progress':
                        # 清除除了进行中任务外的所有任务
                        conn.execute('DELETE FROM tasks WHERE status != ?', (TaskStatus.IN_PROGRESS,))
                    else:
                        # 将前端状态映射为数据库状态
                        status_cn = self.STATUS_MAP.get(status, status)
                        conn.execute('DELETE FROM tasks WHERE status = ?', (status_cn,))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error clearing tasks: {e}")
                return False

    def delete_task(self, task_id: str) -> bool:
        """删除单个任务"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error deleting task: {e}")
                return False

    def migrate_memory_tasks(self, memory_tasks: Dict) -> bool:
        """将内存中的任务迁移到数据库"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    for task_id, task_info in memory_tasks.items():
                        log_content = task_info.log_buffer.getvalue() if hasattr(task_info, 'log_buffer') else ""
                        conn.execute('''
                            INSERT OR REPLACE INTO tasks
                            (id, status, error, log, filename, progress, downloaded,
                             total_size, speed, url, mode, metadata, comicinfo,
                             output_path, target_path, pending_changes, repack_status,
                             move_status, last_error, cover_url, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            task_id,
                            self.STATUS_MAP.get(task_info.status, task_info.status),
                            task_info.error,
                            log_content,
                            task_info.filename,
                            task_info.progress,
                            task_info.downloaded,
                            task_info.total_size,
                            task_info.speed,
                            getattr(task_info, "url", None),
                            getattr(task_info, "mode", None),
                            self._serialize_json(getattr(task_info, "metadata", None)),
                            self._serialize_json(getattr(task_info, "comicinfo", None)),
                            getattr(task_info, "output_path", None),
                            getattr(task_info, "target_path", None),
                            self._serialize_json(getattr(task_info, "pending_changes", None)),
                            getattr(task_info, "repack_status", None),
                            getattr(task_info, "move_status", None),
                            getattr(task_info, "last_error", None),
                            getattr(task_info, "cover_url", None),
                            now,
                            now
                        ))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error migrating tasks: {e}")
                return False

    def _serialize_json(self, value):
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value

    def _deserialize_task(self, task: Dict) -> Dict:
        for key in ("metadata", "comicinfo", "pending_changes"):
            value = task.get(key)
            if isinstance(value, str) and value:
                try:
                    task[key] = json.loads(value)
                except json.JSONDecodeError:
                    pass
        return task


    def set_global_state(self, key: str, value: str) -> bool:
        """设置全局状态值"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.execute('INSERT OR REPLACE INTO global (key, value) VALUES (?, ?)', (key, value))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error setting global state: {e}")
                return False

    def get_global_state(self, key: str) -> Optional[str]:
        """获取全局状态值"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('SELECT value FROM global WHERE key = ?', (key,))
                    row = cursor.fetchone()
                    return row[0] if row else None
            except sqlite3.Error as e:
                print(f"Database error getting global state: {e}")
                return None

    def upsert_eh_favorites(self, favorites: List[Dict]) -> bool:
        """将 E-Hentai 收藏夹数据添加或更新到数据库 (UPSERT)"""
        with self.lock:
            favorites_to_upsert = []
            for fav in favorites:
                gid, token = parse_gallery_url(fav.get('url', ''))
                if gid and token:
                    favorites_to_upsert.append({
                        'gid': gid,
                        'token': token,
                        'originaltitle': fav.get('title'),
                        'favcat': fav.get('favcat'),
                        'added': fav.get('added')
                    })

            if not favorites_to_upsert:
                return True

            try:
                with self._get_conn() as conn:
                    conn.executemany('''
                        INSERT INTO eh_favorites (gid, token, originaltitle, favcat, added)
                        VALUES (:gid, :token, :originaltitle, :favcat, :added)
                        ON CONFLICT(gid) DO UPDATE SET
                            token = excluded.token,
                            originaltitle = excluded.originaltitle,
                            favcat = excluded.favcat,
                            added = excluded.added
                    ''', favorites_to_upsert)
                    conn.commit()
                
                # 更新缓存：找出最新的 added 时间
                added_times = [f['added'] for f in favorites_to_upsert if f.get('added')]
                if added_times:
                    latest = max(added_times)
                    if self._latest_added_cache is None or latest > self._latest_added_cache:
                        self._latest_added_cache = latest
                
                return True
            except sqlite3.Error as e:
                print(f"Database error upserting EH favorites: {e}")
                return False

    def add_eh_favorites(self, favorites: List[Dict]) -> bool:
        """添加 E-Hentai 收藏夹数据到数据库（不更新已存在的记录）"""
        with self.lock:
            favorites_to_add = []
            for fav in favorites:
                gid, token = parse_gallery_url(fav.get('url', ''))
                if gid and token:
                    favorites_to_add.append({
                        'gid': gid,
                        'token': token,
                        'title': fav.get('title'),
                        'originaltitle': fav.get('originaltitle'),
                        'favcat': fav.get('favcat')
                    })

            if not favorites_to_add:
                return True

            try:
                with self._get_conn() as conn:
                    conn.executemany('''
                        INSERT OR IGNORE INTO eh_favorites (gid, token, title, originaltitle, favcat)
                        VALUES (:gid, :token, :title, :originaltitle, :favcat)
                    ''', favorites_to_add)
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error adding EH favorites: {e}")
                return False

    def get_eh_favorites_by_favcat(self, favcat_list: List[str]) -> List[Dict]:
        """根据收藏夹分类ID获取所有画廊"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    placeholders = ','.join('?' for _ in favcat_list)
                    query = f"SELECT gid, token, favcat FROM eh_favorites WHERE favcat IN ({placeholders})"
                    cursor = conn.execute(query, favcat_list)
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting EH favorites by favcat: {e}")
                return []

    def delete_eh_favorites_by_gids(self, gids: List[int]) -> bool:
        """根据 GID 列表删除收藏夹记录"""
        if not gids:
            return True
        with self.lock:
            try:
                with self._get_conn() as conn:
                    placeholders = ','.join('?' for _ in gids)
                    query = f"DELETE FROM eh_favorites WHERE gid IN ({placeholders})"
                    conn.execute(query, gids)
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error deleting EH favorites: {e}")
                return False

    def get_eh_favorite_by_gid(self, gid: int) -> Optional[Dict]:
        """根据 GID 获取单个收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE gid = ?', (gid,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting EH favorite by GID: {e}")
                return None

    def get_undownloaded_favorites(self) -> List[Dict]:
        """获取所有尚未下载的收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE downloaded = ?', (False,))
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting undownloaded favorites: {e}")
                return []

    def mark_favorite_as_downloaded(self, gid: int) -> bool:
        """将指定 GID 的收藏夹项目标记为已下载"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET downloaded = ? WHERE gid = ?', (True, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error marking favorite as downloaded: {e}")
                return False

    def update_favorite_komga_id(self, gid: int, komga_id: str, komga_title: str) -> bool:
        """将指定 GID 的收藏夹项目的 Komga ID 记录下来，并标记为已下载，同时将 Komga 中的标题写入 title 字段"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET komga = ?, downloaded = ?, title = ? WHERE gid = ?', (komga_id, True, komga_title, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error updating favorite's Komga ID: {e}")
                return False

    def update_favorite_favcat(self, gid: int, favcat: str) -> bool:
        """更新指定 GID 的收藏夹项目的 favcat"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('UPDATE eh_favorites SET favcat = ? WHERE gid = ?', (favcat, gid))
                    conn.commit()
                    return cursor.rowcount > 0
            except sqlite3.Error as e:
                print(f"Database error updating favorite's favcat: {e}")
                return False

    def get_favorites_without_komga_id(self) -> List[Dict]:
        """获取所有 komga 字段为空的收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE komga IS NULL')
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting favorites without komga id: {e}")
                return []

    def get_favorite_by_komga_id(self, komga_id: str) -> Optional[Dict]:
        """根据 Komga Book ID 获取单个收藏夹项目"""
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM eh_favorites WHERE komga = ?', (komga_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting favorite by Komga ID: {e}")
                return None

    def get_latest_added_time(self) -> Optional[str]:
        """获取最新的收藏时间（带缓存）"""
        # 如果缓存存在，直接返回
        if self._latest_added_cache is not None:
            return self._latest_added_cache
        
        # 缓存为空时查询数据库
        with self.lock:
            try:
                with self._get_conn() as conn:
                    cursor = conn.execute('SELECT MAX(added) FROM eh_favorites')
                    row = cursor.fetchone()
                    self._latest_added_cache = row[0] if row and row[0] else None
                    return self._latest_added_cache
            except sqlite3.Error as e:
                print(f"Database error getting latest added time: {e}")
                return None

    def upsert_hath_status(self, clients: List[Dict]) -> bool:
        """
        更新 H@H 客户端状态
        
        Args:
            clients: 客户端状态列表，每个元素包含 client_id, client, status 等字段
        
        Returns:
            操作是否成功
        """
        if not clients:
            return True
        
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    
                    for client in clients:
                        client_id = client.get('client_id')
                        if not client_id:
                            continue
                        
                        # 获取上一次的状态
                        cursor = conn.execute(
                            'SELECT status FROM hath_status WHERE client_id = ?',
                            (client_id,)
                        )
                        row = cursor.fetchone()
                        last_status = row[0] if row else None
                        
                        current_status = client.get('status')
                        
                        # 如果状态发生变化，更新 status_changed_at
                        if last_status != current_status:
                            status_changed_at = now
                        else:
                            # 保持原有的 status_changed_at
                            cursor = conn.execute(
                                'SELECT status_changed_at FROM hath_status WHERE client_id = ?',
                                (client_id,)
                            )
                            row = cursor.fetchone()
                            status_changed_at = row[0] if row else now
                        
                        # UPSERT 操作
                        conn.execute('''
                            INSERT INTO hath_status (
                                client_id, client, status, last_status, created, last_seen,
                                files_served, client_ip, port, version, max_speed, trust,
                                quality, hitrate, hathrate, country, last_check, status_changed_at
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(client_id) DO UPDATE SET
                                client = excluded.client,
                                last_status = hath_status.status,
                                status = excluded.status,
                                created = excluded.created,
                                last_seen = excluded.last_seen,
                                files_served = excluded.files_served,
                                client_ip = excluded.client_ip,
                                port = excluded.port,
                                version = excluded.version,
                                max_speed = excluded.max_speed,
                                trust = excluded.trust,
                                quality = excluded.quality,
                                hitrate = excluded.hitrate,
                                hathrate = excluded.hathrate,
                                country = excluded.country,
                                last_check = excluded.last_check,
                                status_changed_at = excluded.status_changed_at
                        ''', (
                            client_id,
                            client.get('client'),
                            current_status,
                            last_status,
                            client.get('created'),
                            client.get('last_seen'),
                            client.get('files_served'),
                            client.get('client_ip'),
                            client.get('port'),
                            client.get('version'),
                            client.get('max_speed'),
                            client.get('trust'),
                            client.get('quality'),
                            client.get('hitrate'),
                            client.get('hathrate'),
                            client.get('country'),
                            now,
                            status_changed_at
                        ))
                    
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error upserting H@H status: {e}")
                return False

    def get_hath_status(self, client_id: Optional[int] = None) -> Optional[Dict] | List[Dict]:
        """
        获取 H@H 客户端状态
        
        Args:
            client_id: 客户端 ID，如果为 None 则返回所有客户端
        
        Returns:
            客户端状态字典或列表
        """
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    
                    if client_id is not None:
                        cursor = conn.execute(
                            'SELECT * FROM hath_status WHERE client_id = ?',
                            (client_id,)
                        )
                        row = cursor.fetchone()
                        return dict(row) if row else None
                    else:
                        cursor = conn.execute('SELECT * FROM hath_status')
                        return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting H@H status: {e}")
                return None

    def get_hath_status_changes(self) -> List[Dict]:
        """
        获取状态发生变化的 H@H 客户端
        
        Returns:
            状态发生变化的客户端列表
        """
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('''
                        SELECT * FROM hath_status 
                        WHERE status != last_status OR last_status IS NULL
                    ''')
                    return [dict(row) for row in cursor.fetchall()]
            except sqlite3.Error as e:
                print(f"Database error getting H@H status changes: {e}")
                return []

    def normalize_url(self, url: str) -> tuple[str, str]:
        """
        规范化 URL 并识别站点类型
        
        Args:
            url: 原始 URL
        
        Returns:
            (normalized_url, site_type)
        """
        from urllib.parse import urlparse
        
        # 解析 URL
        parsed = urlparse(url.lower())
        
        # 去除协议
        domain = parsed.netloc or parsed.path.split('/')[0]
        path = parsed.path if parsed.netloc else '/' + '/'.join(parsed.path.split('/')[1:])
        
        # 统一 exhentai 为 e-hentai
        if 'exhentai.org' in domain:
            domain = 'e-hentai.org'
        
        # 去除 www 前缀
        domain = domain.replace('www.', '')
        
        # 去除尾部斜杠
        path = path.rstrip('/')
        
        # 组合规范化 URL
        normalized = f"{domain}{path}"
        
        # 识别站点类型
        if 'e-hentai.org' in domain or 'exhentai.org' in domain:
            site_type = 'e-hentai'
        elif 'nhentai.net' in domain:
            site_type = 'nhentai'
        elif 'hitomi.la' in domain:
            site_type = 'hitomi'
        elif 'hdoujin.org' in domain:
            site_type = 'hdoujin'
        else:
            site_type = 'other'
        
        return normalized, site_type

    def upsert_komga_url_index(self, urls: List[Dict]) -> bool:
        """
        批量插入或更新 Komga URL 索引
        
        Args:
            urls: URL 列表，每个元素包含 url, book_id, original_url, site_type
        
        Returns:
            操作是否成功
        """
        if not urls:
            return True
        
        with self.lock:
            try:
                with self._get_conn() as conn:
                    now = datetime.now(timezone.utc).isoformat()
                    
                    # 准备数据
                    data_to_upsert = []
                    for item in urls:
                        url = item.get('url')
                        if not url:
                            continue
                        
                        normalized_url, site_type = self.normalize_url(url)
                        data_to_upsert.append({
                            'normalized_url': normalized_url,
                            'book_id': item.get('book_id'),
                            'original_url': item.get('original_url', url),
                            'site_type': item.get('site_type', site_type),
                            'updated_at': now
                        })
                    
                    if not data_to_upsert:
                        return True
                    
                    # 批量 UPSERT
                    conn.executemany('''
                        INSERT INTO komga_url_index 
                        (normalized_url, book_id, original_url, site_type, updated_at)
                        VALUES (:normalized_url, :book_id, :original_url, :site_type, :updated_at)
                        ON CONFLICT(normalized_url) DO UPDATE SET
                            book_id = excluded.book_id,
                            original_url = excluded.original_url,
                            site_type = excluded.site_type,
                            updated_at = excluded.updated_at
                    ''', data_to_upsert)
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error upserting Komga URL index: {e}")
                return False

    def check_urls_exist(self, urls: List[str]) -> Dict[str, bool]:
        """
        批量检查 URL 是否已存在
        
        Args:
            urls: URL 列表
        
        Returns:
            {normalized_url: exists}
        """
        if not urls:
            return {}
        
        with self.lock:
            try:
                with self._get_conn() as conn:
                    # 规范化所有 URL
                    normalized_urls = [self.normalize_url(url)[0] for url in urls]
                    
                    # 构建查询
                    placeholders = ','.join('?' for _ in normalized_urls)
                    query = f"SELECT normalized_url FROM komga_url_index WHERE normalized_url IN ({placeholders})"
                    
                    cursor = conn.execute(query, normalized_urls)
                    existing = {row[0] for row in cursor.fetchall()}
                    
                    # 构建结果字典
                    result = {norm_url: norm_url in existing for norm_url in normalized_urls}
                    return result
            except sqlite3.Error as e:
                print(f"Database error checking URLs exist: {e}")
                return {url: False for url in urls}

    def query_book_ids_by_urls(self, urls: List[str]) -> Dict[str, Optional[Dict]]:
        """
        批量查询 URL 对应的 Book ID
        
        Args:
            urls: URL 列表
        
        Returns:
            {normalized_url: {book_id, original_url, site_type} or None}
        """
        if not urls:
            return {}
        
        with self.lock:
            try:
                with self._get_conn() as conn:
                    conn.row_factory = sqlite3.Row
                    
                    # 规范化所有 URL
                    url_mapping = {self.normalize_url(url)[0]: url for url in urls}
                    normalized_urls = list(url_mapping.keys())
                    
                    # 构建查询
                    placeholders = ','.join('?' for _ in normalized_urls)
                    query = f"""
                        SELECT normalized_url, book_id, original_url, site_type 
                        FROM komga_url_index 
                        WHERE normalized_url IN ({placeholders})
                    """
                    
                    cursor = conn.execute(query, normalized_urls)
                    results = {}
                    
                    for row in cursor.fetchall():
                        results[row['normalized_url']] = {
                            'book_id': row['book_id'],
                            'original_url': row['original_url'],
                            'site_type': row['site_type']
                        }
                    
                    # 为未找到的 URL 添加 None
                    for norm_url in normalized_urls:
                        if norm_url not in results:
                            results[norm_url] = None
                    
                    return results
            except sqlite3.Error as e:
                print(f"Database error querying book IDs by URLs: {e}")
                return {self.normalize_url(url)[0]: None for url in urls}

# 全局数据库实例
task_db = TaskDatabase()

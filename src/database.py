import sqlite3
import json
import threading
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple

class TaskDatabase:
    def __init__(self, db_path: str = './data/tasks.db'):
        self.db_path = db_path
        self.lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """初始化数据库表"""
        with sqlite3.connect(self.db_path) as conn:
            # 检查是否需要添加新字段
            cursor = conn.execute("PRAGMA table_info(tasks)")
            columns = [row[1] for row in cursor.fetchall()]

            # 创建表（如果不存在）
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
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # 如果表已存在但缺少新字段，添加它们
            if 'url' not in columns:
                conn.execute('ALTER TABLE tasks ADD COLUMN url TEXT')
            if 'mode' not in columns:
                conn.execute('ALTER TABLE tasks ADD COLUMN mode TEXT')

            conn.commit()
    
    def add_task(self, task_id: str, status: str = "进行中",
                 filename: Optional[str] = None, error: Optional[str] = None,
                 url: Optional[str] = None, mode: Optional[str] = None) -> bool:
        """添加新任务"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute('''
                        INSERT OR REPLACE INTO tasks
                        (id, status, filename, error, url, mode, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (task_id, status, filename, error, url, mode,
                          datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error adding task: {e}")
                return False
    
    def update_task(self, task_id: str, status: Optional[str] = None, error: Optional[str] = None,
                   log: Optional[str] = None, filename: Optional[str] = None, progress: Optional[int] = None,
                   downloaded: Optional[int] = None, total_size: Optional[int] = None, speed: Optional[int] = None) -> bool:
        """更新任务信息"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    # 构建动态更新语句
                    updates = []
                    params = []
                    
                    if status is not None:
                        updates.append("status = ?")
                        params.append(status)
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
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    cursor = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
                    row = cursor.fetchone()
                    return dict(row) if row else None
            except sqlite3.Error as e:
                print(f"Database error getting task: {e}")
                return None
    
    def get_tasks(self, status_filter: Optional[str] = None, page: int = 1,
                  page_size: int = 20) -> Tuple[List[Dict], int]:
        """获取任务列表，支持分页和状态过滤"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    conn.row_factory = sqlite3.Row
                    
                    # 构建查询条件
                    where_clause = ""
                    params = []
                    
                    if status_filter:
                        if status_filter == 'in-progress':
                            where_clause = "WHERE status = ?"
                            params.append('进行中')
                        elif status_filter == 'completed':
                            where_clause = "WHERE status = ?"
                            params.append('完成')
                        elif status_filter == 'cancelled':
                            where_clause = "WHERE status = ?"
                            params.append('取消')
                        elif status_filter == 'failed':
                            where_clause = "WHERE status = ?"
                            params.append('错误')
                    
                    # 获取总数
                    count_query = f"SELECT COUNT(*) FROM tasks {where_clause}"
                    cursor = conn.execute(count_query, params)
                    total = cursor.fetchone()[0]
                    
                    # 获取分页数据
                    offset = (page - 1) * page_size
                    data_query = f"""
                        SELECT * FROM tasks {where_clause}
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                    """
                    params.extend([page_size, offset])
                    
                    cursor = conn.execute(data_query, params)
                    tasks = [dict(row) for row in cursor.fetchall()]
                    
                    return tasks, total
            except sqlite3.Error as e:
                print(f"Database error getting tasks: {e}")
                return [], 0
    
    def clear_tasks(self, status: str) -> bool:
        """清除指定状态的任务"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    if status == "失败":
                        conn.execute('DELETE FROM tasks WHERE status = ?', ('错误',))
                    elif status == "取消":
                        conn.execute('DELETE FROM tasks WHERE status = ?', ('取消',))
                    else:
                        conn.execute('DELETE FROM tasks WHERE status = ?', (status,))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error clearing tasks: {e}")
                return False
    

    def migrate_memory_tasks(self, memory_tasks: Dict) -> bool:
        """将内存中的任务迁移到数据库"""
        with self.lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    for task_id, task_info in memory_tasks.items():
                        log_content = task_info.log_buffer.getvalue() if hasattr(task_info, 'log_buffer') else ""
                        conn.execute('''
                            INSERT OR REPLACE INTO tasks
                            (id, status, error, log, filename, progress, downloaded, total_size, speed, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            task_id,
                            task_info.status,
                            task_info.error,
                            log_content,
                            task_info.filename,
                            task_info.progress,
                            task_info.downloaded,
                            task_info.total_size,
                            task_info.speed,
                            datetime.now(timezone.utc).isoformat(),
                            datetime.now(timezone.utc).isoformat()
                        ))
                    conn.commit()
                return True
            except sqlite3.Error as e:
                print(f"Database error migrating tasks: {e}")
                return False

# 全局数据库实例
task_db = TaskDatabase()
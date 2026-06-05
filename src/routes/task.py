"""
Task 相关路由
这个模块包含所有与任务管理相关的 API 路由
使用 Flask Blueprint 实现
"""
from flask import Blueprint, current_app, request
import sqlite3
from utils import json_response

def enrich_task_data(task_dict, app):
    """为任务实体注入 has_path_difference 字段以支持前端智能移动亮起交互"""
    if not task_dict:
        return task_dict
    from utils_move import calculate_task_move_path
    import os
    current_path = task_dict.get('output_path')
    suggested = calculate_task_move_path(task_dict, app)
    
    # 将只读的 sqlite3.Row 或内存 dict 统一规范化为可写 dict
    task_data = dict(task_dict)
    
    if current_path and suggested and task_dict.get('status') == '完成':
        task_data['has_path_difference'] = os.path.normpath(current_path) != os.path.normpath(suggested)
        task_data['target_path'] = suggested
    else:
        task_data['has_path_difference'] = False
    return task_data

# 创建 Blueprint 实例
bp = Blueprint('task', __name__)

@bp.route('/api/tasks/stats', methods=['GET'])
def get_task_stats():
    """获取任务统计信息"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入 TaskStatus 枚举
        from utils import TaskStatus

        with sqlite3.connect('./data/tasks.db') as conn:
            conn.row_factory = sqlite3.Row
            # 获取各种状态的任务数量
            cursor = conn.execute('''
                SELECT
                    status,
                    COUNT(*) as count
                FROM tasks
                GROUP BY status
            ''')
            status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

            # 获取总任务数
            cursor = conn.execute('SELECT COUNT(*) as total FROM tasks')
            total_tasks = cursor.fetchone()['total']

            # 获取进行中任务数
            in_progress = status_counts.get(TaskStatus.IN_PROGRESS, 0)

            # 获取已完成任务数
            completed = status_counts.get(TaskStatus.COMPLETED, 0)

            # 获取取消任务数
            cancelled = status_counts.get(TaskStatus.CANCELLED, 0)

            # 获取失败任务数（只包括错误）
            failed = status_counts.get(TaskStatus.ERROR, 0)

            return json_response({
                'total': total_tasks,
                'in_progress': in_progress,
                'completed': completed,
                'cancelled': cancelled,
                'failed': failed,
                'status_counts': status_counts
            })

    except sqlite3.Error as e:
        if global_logger:
            global_logger.error(f"Database error getting task stats: {e}")
        return json_response({'error': 'Failed to get task statistics'}), 500

@bp.route('/api/covers/<filename>', methods=['GET'])
def get_cover(filename):
    """获取任务的本地缓存封面，若丢失则尝试重新下载或重定向回原始 URL"""
    import os
    from flask import send_from_directory, redirect
    from utils import check_dirs, download_cover
    from database import task_db

    cover_dir = os.path.abspath(check_dirs('./data/covers'))
    file_path = os.path.join(cover_dir, filename)
    task_id = os.path.splitext(filename)[0]
    
    # 忽略前端请求的扩展名，直接查找该 task_id 的任何本地缓存文件
    import glob
    matching_files = glob.glob(os.path.join(cover_dir, f"{task_id}.*"))
    if matching_files:
        # 取找到的第一个文件（真实存在的扩展名，比如 .webp）并返回
        actual_filename = os.path.basename(matching_files[0])
        return send_from_directory(cover_dir, actual_filename)
        
    # 如果文件不存在，尝试从数据库获取原始链接重新下载
    task_info = task_db.get_task(task_id)
    if task_info and task_info.get('metadata'):
        metadata = task_info['metadata']
        if isinstance(metadata, dict):
            raw_cover_url = metadata.get('thumb') or metadata.get('thumbnail_url')
            if raw_cover_url:
                # 尝试重新下载
                new_url = download_cover(raw_cover_url, task_id, current_app.config)
                if new_url.startswith('/api/covers/'):
                    # 重新下载成功，提取新的文件名并返回
                    new_filename = new_url.split('/')[-1]
                    return send_from_directory(cover_dir, new_filename)
                else:
                    # 下载失败，作为最后手段直接 302 重定向到原始直链
                    return redirect(raw_cover_url)
                    
    return json_response({'error': 'Cover not found and cannot be recovered'}), 404

@bp.route('/api/tasks/clear', methods=['POST'])
def clear_tasks():
    """清理指定状态的任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        status_to_clear = request.args.get('status')
        if not status_to_clear:
            return json_response({'error': 'No status provided to clear'}), 400

        # 导入必要的模块和变量
        from database import task_db
        from utils import TaskStatus

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 从数据库清除任务
        success = task_db.clear_tasks(status_to_clear)
        if not success:
            return json_response({'error': 'Failed to clear tasks from database'}), 500

        # 同时从内存清除对应任务
        with tasks_lock:
            tasks_to_keep = {}
            for tid, task_info in tasks.items():
                should_clear = False

                if status_to_clear == "all_except_in_progress":
                    # 清除除了进行中任务外的所有任务
                    should_clear = task_info.status != TaskStatus.IN_PROGRESS
                elif status_to_clear == "failed":
                    # 清除失败状态的任务（对应数据库中的"错误"状态）
                    should_clear = task_info.status == TaskStatus.ERROR
                elif status_to_clear == "completed":
                    # 清除已完成的任务
                    should_clear = task_info.status == TaskStatus.COMPLETED
                elif status_to_clear == "cancelled":
                    # 清除取消的任务
                    should_clear = task_info.status == TaskStatus.CANCELLED
                elif status_to_clear == "in-progress":
                    # 清除进行中的任务
                    should_clear = task_info.status == TaskStatus.IN_PROGRESS
                else:
                    # 直接状态匹配
                    should_clear = task_info.status == status_to_clear

                if should_clear:
                    # 清除日志缓冲区
                    if hasattr(task_info, 'log_buffer'):
                        task_info.log_buffer.close()
                else:
                    tasks_to_keep[tid] = task_info

            tasks.clear()
            tasks.update(tasks_to_keep)

        return json_response({'message': f'Tasks with status "{status_to_clear}" cleared successfully'}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error clearing tasks: {e}")
        return json_response({'error': f'Failed to clear tasks: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>')
def get_task(task_id):
    """获取指定任务的完整信息（双数据源查询：内存 -> 数据库）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from database import task_db

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 首先检查内存中的任务
        with tasks_lock:
            memory_task = tasks.get(task_id)
            if memory_task:
                # 把内存中任务的所有熟悉转换为字典，避免遗漏 output_path 等新字段
                task_data = {
                    'id': task_id,
                    'status': memory_task.status,
                    'error': memory_task.error,
                    'filename': memory_task.filename,
                    'progress': memory_task.progress,
                    'downloaded': memory_task.downloaded,
                    'total_size': memory_task.total_size,
                    'speed': memory_task.speed,
                    'url': getattr(memory_task, 'url', None),
                    'mode': getattr(memory_task, 'mode', None),
                    'metadata': getattr(memory_task, 'metadata', None),
                    'comicinfo': getattr(memory_task, 'comicinfo', None),
                    'output_path': getattr(memory_task, 'output_path', None),
                    'target_path': getattr(memory_task, 'target_path', None),
                    'cover_url': getattr(memory_task, 'cover_url', None),
                    'log': memory_task.log_buffer.getvalue()
                }
                return json_response(enrich_task_data(task_data, current_app))

        # 如果内存中没有，检查数据库
        db_task = task_db.get_task(task_id)
        if db_task:
            return json_response(enrich_task_data(db_task, current_app))

        return json_response({'error': 'Task not found'}), 404

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting task {task_id}: {e}")
        return json_response({'error': f'Failed to get task: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>', methods=['DELETE'])
def delete_task(task_id):
    """删除指定任务（仅限非进行中的任务）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from utils import TaskStatus
        from database import task_db

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 首先检查任务是否存在
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 检查任务状态，不允许删除进行中的任务
        if task_info['status'] == TaskStatus.IN_PROGRESS:
            return json_response({'error': 'Cannot delete task that is in progress'}), 400

        # 检查是否要求同时删除物理文件
        delete_file = request.args.get('delete_file', 'false').lower() == 'true'
        output_path = task_info.get('output_path')
        
        # 从内存中删除任务（如果存在）
        with tasks_lock:
            if task_id in tasks:
                # 关闭日志缓冲区
                if hasattr(tasks[task_id], 'log_buffer'):
                    tasks[task_id].log_buffer.close()
                del tasks[task_id]

        # 如果要求删除物理文件且路径存在，则尝试删除文件
        file_deleted_msg = ""
        if delete_file and output_path:
            import os
            import shutil
            try:
                if os.path.exists(output_path):
                    if os.path.isdir(output_path):
                        shutil.rmtree(output_path)
                    else:
                        os.remove(output_path)
                        # 清理可能残留的 aria2 后缀文件
                        aria2_file = f"{output_path}.aria2"
                        if os.path.exists(aria2_file):
                            os.remove(aria2_file)
                    file_deleted_msg = " and physical file/directory removed"
                    if global_logger:
                        global_logger.info(f"Physical file for task {task_id} removed: {output_path}")
                else:
                    file_deleted_msg = " (physical file not found)"
            except Exception as e:
                file_deleted_msg = f" (failed to remove physical file: {e})"
                if global_logger:
                    global_logger.error(f"Failed to remove physical file for task {task_id} at {output_path}: {e}")

        # 从数据库删除任务
        success = task_db.delete_task(task_id)
        if not success:
            return json_response({'error': 'Failed to delete task from database'}), 500

        # 清理可能存在的本地封面缓存
        cover_url = task_info.get('cover_url')
        if cover_url and cover_url.startswith('/api/covers/'):
            import os
            try:
                filename = cover_url.split('/')[-1]
                cover_path = os.path.join(os.path.abspath('./data/covers'), filename)
                if os.path.exists(cover_path):
                    os.remove(cover_path)
            except Exception as e:
                if global_logger:
                    global_logger.warning(f"Failed to remove cover file for task {task_id}: {e}")

        if global_logger:
            global_logger.info(f"Task {task_id} deleted successfully{file_deleted_msg}")
        return json_response({'message': f'Task deleted successfully{file_deleted_msg}'}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error deleting task {task_id}: {e}")
        return json_response({'error': f'Failed to delete task: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消/停止指定任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from utils import TaskStatus
        from database import task_db

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        with tasks_lock:
            task = tasks.get(task_id)
        if not task:
            return json_response({'error': 'Task not found'}), 404

        # 设置取消标志
        task.cancelled = True

        # 检查任务是否正在使用 Aria2 下载
        aria2_gid = None
        with tasks_lock:
            if task.aria2_gid:
                aria2_gid = task.aria2_gid
                if global_logger:
                    global_logger.info(f"检测到任务 {task_id} 正在使用 Aria2 下载 (gid: {aria2_gid})，尝试取消 Aria2 任务")

        # 如果任务正在使用 Aria2，主动发送取消指令
        if aria2_gid:
            try:
                from providers import aria2
                aria2_server = current_app.config.get('ARIA2_SERVER')
                aria2_token = current_app.config.get('ARIA2_TOKEN')
                
                if aria2_server and aria2_token:
                    # 按需创建 Aria2RPC 实例
                    rpc = aria2.Aria2RPC(url=aria2_server, token=aria2_token, logger=global_logger)
                    remove_result = rpc.remove(aria2_gid)
                    if global_logger:
                        if remove_result.get('result'):
                            global_logger.info(f"成功向 Aria2 发送取消指令 (gid: {aria2_gid})")
                        else:
                            global_logger.warning(f"Aria2 取消指令可能失败: {remove_result}")
            except Exception as e:
                if global_logger:
                    global_logger.warning(f"向 Aria2 发送取消指令时出错: {e}")

        cancelled = task.future.cancel()
        if cancelled:
            with tasks_lock:
                task.status = TaskStatus.CANCELLED
            # 更新数据库状态
            task_db.update_task(task_id, status=TaskStatus.CANCELLED)
            if global_logger:
                global_logger.info(f"Task {task_id} cancelled successfully")
            return json_response({'message': 'Task cancelled'})
        else:
            # 即使 future.cancel() 返回 False（任务已在运行），
            # 取消标志已设置，且 Aria2 任务（如果有）已被取消
            # 任务会在下一个检查点自然终止
            if global_logger:
                global_logger.info(f"Task {task_id} is running, cancel flag set, will stop at next checkpoint")
            return json_response({'message': 'Task cancel requested (任务正在运行，将在检查点处停止)'}), 200

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error stopping task {task_id}: {e}")
        return json_response({'error': f'Failed to stop task: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/retry', methods=['POST'])
def retry_task(task_id):
    """重试失败的任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from utils import TaskStatus
        from database import task_db
        from datetime import datetime, timezone
        import sqlite3
        import main

        # 从 current_app.config 获取 tasks、tasks_lock 和 executor
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')
        executor = current_app.config.get('EXECUTOR')

        if not tasks_lock or not executor:
            return json_response({'error': 'Server not properly initialized'}), 500

        # 从数据库获取任务信息
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 检查任务状态是否为失败或取消
        if task_info['status'] not in (TaskStatus.ERROR, TaskStatus.CANCELLED):
            return json_response({'error': 'Only failed or cancelled tasks can be retried'}), 400

        # 检查是否有URL信息
        if not task_info.get('url'):
            return json_response({'error': 'Task URL information is missing, cannot retry'}), 400

        # 获取URL、mode和favcat
        url = task_info['url']
        mode = task_info.get('mode')
        favcat = task_info.get('favcat')  # 可能是 None、字符串 '0'-'9'

        # 创建新的任务ID
        new_task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')

        # 添加新任务到数据库
        task_db.add_task(new_task_id, status=TaskStatus.IN_PROGRESS, url=url, mode=mode, favcat=favcat)

        # 删除原来的失败任务
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                conn.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
                conn.commit()
            if global_logger:
                global_logger.info(f"已从数据库删除失败任务 {task_id}")
        except sqlite3.Error as e:
            if global_logger:
                global_logger.error(f"删除失败任务时发生数据库错误: {e}")

        # 从内存中删除原来的失败任务
        with tasks_lock:
            if task_id in tasks:
                # 关闭日志缓冲区
                if hasattr(tasks[task_id], 'log_buffer'):
                    tasks[task_id].log_buffer.close()
                del tasks[task_id]

        # 创建新的任务执行
        # 将 favcat 从字符串转换回原始格式（'0'-'9' 或 False）
        if favcat and favcat.isdigit():
            favcat_param = favcat  # 保持为字符串 '0'-'9'
        else:
            favcat_param = False
        
        logger, log_buffer = main.get_task_logger(new_task_id)
        
        # 从 current_app.config 获取函数和类
        get_task_logger = current_app.config.get('GET_TASK_LOGGER')
        task_failure_processing = current_app.config.get('TASK_FAILURE_PROCESSING')
        download_gallery_task = current_app.config.get('DOWNLOAD_GALLERY_TASK')
        TaskInfo = current_app.config.get('TASK_INFO_CLASS')
        
        # 动态应用装饰器
        decorated_download_task = task_failure_processing(url, new_task_id, logger, tasks, tasks_lock)(download_gallery_task)
        
        future = executor.submit(decorated_download_task, url, mode, new_task_id, logger, favcat_param, tasks, tasks_lock)

        # 更新内存中的任务信息
        with tasks_lock:
            tasks[new_task_id] = TaskInfo(future, logger, log_buffer)

        if global_logger:
            global_logger.info(f"Task retry started with new ID {new_task_id}")
        return json_response({'message': f'Task retry started with new ID {new_task_id}', 'task_id': new_task_id}), 202

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error retrying task {task_id}: {e}")
        return json_response({'error': f'Failed to retry task: {str(e)}'}), 500

@bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    """获取任务列表（支持分页和状态过滤）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        # 导入必要的模块和变量
        from database import task_db
        from utils import TaskStatus
        import sqlite3

        # 从 current_app.config 获取 tasks 和 tasks_lock
        tasks = current_app.config.get('TASKS', {})
        tasks_lock = current_app.config.get('TASKS_LOCK')

        if not tasks_lock:
            return json_response({'error': 'Server not properly initialized'}), 500

        status_filter = request.args.get('status')
        
        # 安全的参数转换，添加验证
        try:
            page = int(request.args.get('page', 1))
            if page < 1:
                page = 1
        except (ValueError, TypeError):
            page = 1
        
        try:
            page_size = int(request.args.get('page_size', 20))
            if page_size < 1:
                page_size = 20
            elif page_size > 100:  # 限制最大页面大小
                page_size = 100
        except (ValueError, TypeError):
            page_size = 20

        # 从数据库获取任务列表
        db_tasks, total = task_db.get_tasks(status_filter, page, page_size)

        # 合并内存中的活跃任务信息
        with tasks_lock:
            for db_task in db_tasks:
                task_id = db_task['id']
                if task_id in tasks:
                    memory_task = tasks[task_id]
                    # 用内存中的最新信息更新数据库任务
                    db_task.update({
                        'status': memory_task.status,
                        'error': memory_task.error,
                        'log': memory_task.log_buffer.getvalue(),
                        'filename': memory_task.filename,
                        'progress': memory_task.progress,
                        'downloaded': memory_task.downloaded,
                        'total_size': memory_task.total_size,
                        'speed': memory_task.speed
                    })

                    # 同步更新数据库
                    task_db.update_task(
                        task_id,
                        status=memory_task.status,
                        error=memory_task.error,
                        log=memory_task.log_buffer.getvalue(),
                        filename=memory_task.filename,
                        progress=memory_task.progress,
                        downloaded=memory_task.downloaded,
                        total_size=memory_task.total_size,
                        speed=memory_task.speed
                    )

        # 按任务ID降序排序（任务ID基于时间，新的ID更大）
        db_tasks.sort(key=lambda x: x.get('id', ''), reverse=True)

        # 获取各个状态的任务数量统计
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM tasks
                    GROUP BY status
                ''')
                status_counts = {row['status']: row['count'] for row in cursor.fetchall()}

                # 获取各个状态的总数
                all_count = sum(status_counts.values())
                in_progress_count = status_counts.get(TaskStatus.IN_PROGRESS, 0)
                completed_count = status_counts.get(TaskStatus.COMPLETED, 0)
                cancelled_count = status_counts.get(TaskStatus.CANCELLED, 0)
                failed_count = status_counts.get(TaskStatus.ERROR, 0)
        except sqlite3.Error as e:
            if global_logger:
                global_logger.error(f"Database error getting status counts: {e}")
            all_count = total
            in_progress_count = 0
            completed_count = 0
            cancelled_count = 0
            failed_count = 0

        return json_response({
            'tasks': [enrich_task_data(t, current_app) for t in db_tasks],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
            'status_counts': {
                'all': all_count,
                'in-progress': in_progress_count,
                'completed': completed_count,
                'cancelled': cancelled_count,
                'failed': failed_count
            }
        })

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting tasks: {e}")
        return json_response({'error': f'Failed to get tasks: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/metadata', methods=['PATCH'])
def update_task_metadata(task_id):
    """更新任务的元数据（保存编辑结果到 comicinfo 和 pending_changes）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db

        # 获取请求体
        data = request.get_json()
        if not data:
            return json_response({'error': 'No metadata provided'}), 400

        # 检查任务是否存在
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 定义所有支持的 ComicInfo 标准字段
        key_map = {
            'agerating': 'AgeRating', 'languageiso': 'LanguageISO',
            'alternateseries': 'AlternateSeries', 'alternatenumber': 'AlternateNumber',
            'storyarc': 'StoryArc', 'storyarcnumber': 'StoryArcNumber',
            'seriesgroup': 'SeriesGroup', 'coverartist': 'CoverArtist',
            'gtin': 'GTIN', 'number': 'Number', 'series': 'Series',
            'title': 'Title', 'writer': 'Writer', 'penciller': 'Penciller',
            'translator': 'Translator', 'tags': 'Tags', 'web': 'Web',
            'manga': 'Manga', 'genre': 'Genre', 'summary': 'Summary'
        }
        
        # 允许修改并写入的字段，不再严格依赖 config.yaml，而是开放所有支持的规范字段
        # 这样用户在前端手动编辑如 SeriesGroup, Summary 时才能生效
        allowed_keys = set(key_map.values())

        # 检查这些需要在 ComicInfo.xml 中写入的字段是否真的发生了变化
        old_metadata = task_info.get('comicinfo') or {}
        pending_changes_diff = {}
        for key in allowed_keys:
            if key not in data and key not in old_metadata:
                continue
            new_val = data.get(key)
            old_val = old_metadata.get(key)
            
            # 将 None 和空字符串等同处理，避免因为空值类型不一致误触发打包
            new_val_str = str(new_val).strip() if new_val is not None else ""
            old_val_str = str(old_val).strip() if old_val is not None else ""
            if new_val_str != old_val_str:
                pending_changes_diff[key] = new_val

        # 尝试自动进行重新打包物理文件
        import os
        import cbztool
        cbz_path = task_info.get('output_path')
        
        # 默认设定：不需要或成功打包
        pending_changes = {}
        repack_status = 'completed'
        last_error = None
        
        # 性能优化：只有当确实有属于 ComicInfo 配置范围内的字段发生了变化时，才进行物理打包操作
        if pending_changes_diff and cbz_path and os.path.exists(cbz_path):
            # 将新数据按照白名单过滤，只写入配置允许的字段到 ComicInfo.xml
            filtered_metadata = {k: v for k, v in data.items() if k in allowed_keys}
            try:
                # 临时标记重新打包中，以便有据可查
                task_db.update_task(task_id, repack_status='in_progress')
                result = cbztool.update_comicinfo_in_cbz(cbz_path, filtered_metadata, logger=global_logger)
                if not result:
                    pending_changes = pending_changes_diff
                    repack_status = 'failed'
                    last_error = '写入 ComicInfo.xml 失败'
            except Exception as e:
                pending_changes = pending_changes_diff
                repack_status = 'failed'
                last_error = f'自动打包失败: {str(e)}'
        elif pending_changes_diff and cbz_path:
            # 有 output_path 但文件不存在，且确实有待写入 XML 的元数据更改
            pending_changes = pending_changes_diff
            repack_status = 'failed'
            last_error = f'物理文件不存在，无法打包: {cbz_path}'

        # 将提交的数据保存为 comicinfo
        task_db.update_task(
            task_id,
            comicinfo=data,
            pending_changes=pending_changes,
            repack_status=repack_status,
            last_error=last_error
        )

        if global_logger:
            global_logger.info(f"Task {task_id} metadata saved and repack executed (status: {repack_status})")

        # 返回更新且增强后的任务数据
        updated_task = task_db.get_task(task_id)
        return json_response({
            'message': 'Metadata updated and repacked successfully',
            'task': enrich_task_data(updated_task, current_app)
        })

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error updating task metadata {task_id}: {e}")
        return json_response({'error': f'Failed to update metadata: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/repack', methods=['POST'])
def repack_task(task_id):
    """重新打包任务的 CBZ 文件（使用 comicinfo 中的元数据更新 ComicInfo.xml）"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        import cbztool

        # 检查任务是否存在
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 检查是否有 comicinfo
        comicinfo = task_info.get('comicinfo')
        if not comicinfo:
            return json_response({'error': 'No comicinfo available. Save metadata first.'}), 400

        # 确定要操作的文件路径
        cbz_path = task_info.get('output_path')
        if not cbz_path:
            return json_response({'error': 'No output_path set for this task'}), 400

        import os
        if not os.path.exists(cbz_path):
            task_db.update_task(task_id, repack_status='failed', last_error=f'文件不存在: {cbz_path}')
            return json_response({'error': f'CBZ file does not exist: {cbz_path}'}), 404

        # 标记重新打包进行中
        task_db.update_task(task_id, repack_status='in_progress')

        # 根据 config 中的 comicinfo 配置白名单过滤元数据，避免把物理属性（如默认不写入的 Series）误写进 ComicInfo.xml
        comicinfo_config = current_app.config.get('COMICINFO', {}) or {}
        key_map = {
            'agerating': 'AgeRating',
            'languageiso': 'LanguageISO',
            'alternateseries': 'AlternateSeries',
            'alternatenumber': 'AlternateNumber',
            'storyarc': 'StoryArc',
            'storyarcnumber': 'StoryArcNumber',
            'seriesgroup': 'SeriesGroup',
            'coverartist': 'CoverArtist',
            'gtin': 'GTIN',
            'number': 'Number',
            'series': 'Series',
            'title': 'Title',
            'writer': 'Writer',
            'penciller': 'Penciller',
            'translator': 'Translator',
            'tags': 'Tags',
            'web': 'Web',
            'manga': 'Manga',
            'genre': 'Genre'
        }
        allowed_keys = set()
        for k in comicinfo_config.keys():
            allowed_keys.add(key_map.get(k.lower(), k.capitalize()))
            
        filtered_metadata = {k: v for k, v in comicinfo.items() if k in allowed_keys}

        # 执行重新打包（仅替换 ComicInfo.xml）
        result = cbztool.update_comicinfo_in_cbz(cbz_path, filtered_metadata, logger=global_logger)

        if result:
            # 成功：清除 pending_changes，更新状态
            task_db.update_task(
                task_id,
                repack_status='completed',
                pending_changes={},
                last_error=None
            )
            if global_logger:
                global_logger.info(f"Task {task_id} repack completed: {cbz_path}")
            return json_response({'message': 'Repack completed successfully', 'output_path': result})
        else:
            task_db.update_task(task_id, repack_status='failed', last_error='CBZ 更新失败')
            return json_response({'error': 'Repack failed'}), 500

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error repacking task {task_id}: {e}")
        # 更新失败状态
        try:
            from database import task_db as db
            db.update_task(task_id, repack_status='failed', last_error=str(e))
        except Exception:
            pass
        return json_response({'error': f'Failed to repack: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/move-path', methods=['GET'])
def get_task_move_path(task_id):
    """计算任务基于当前元数据和完成后移动配置模板渲染出的建议物理目标路径"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        from utils_move import calculate_task_move_path
        
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404
            
        current_path = task_info.get('output_path')
        if not current_path:
            return json_response({'error': 'No output_path set for this task'}), 400
            
        suggested_path = calculate_task_move_path(task_info, current_app, logger=global_logger)
        
        if not suggested_path:
            return json_response({
                'current_path': current_path,
                'suggested_path': None,
                'has_difference': False,
                'message': '未配置移动模板或渲染失败，使用当前路径'
            })
            
        import os
        has_difference = os.path.normpath(current_path) != os.path.normpath(suggested_path)
        
        return json_response({
            'current_path': current_path,
            'suggested_path': suggested_path,
            'has_difference': has_difference
        })
        
    except Exception as e:
        if global_logger:
            global_logger.error(f"Error calculating task move path {task_id}: {e}")
        return json_response({'error': f'Failed to calculate move path: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/move', methods=['POST'])
def move_task_file(task_id):
    """移动任务的输出文件到新路径"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        from utils_move import calculate_task_move_path
        import os
        import shutil

        # 检查任务是否存在
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        # 获取请求体，支持自动计算目标路径
        data = request.get_json() or {}
        target_path = data.get('target_path')
        
        if not target_path:
            target_path = calculate_task_move_path(task_info, current_app, logger=global_logger)
            if not target_path:
                return json_response({'error': 'No target_path provided and automatic path calculation failed'}), 400

        # 确定源文件路径
        source_path = task_info.get('output_path')
        if not source_path:
            return json_response({'error': 'No output_path set for this task'}), 400

        if not os.path.exists(source_path):
            task_db.update_task(task_id, move_status='failed', last_error=f'源文件不存在: {source_path}')
            return json_response({'error': f'Source file does not exist: {source_path}'}), 404

        # 检查源路径和目标路径是否一致
        if os.path.normpath(source_path) == os.path.normpath(target_path):
            task_db.update_task(task_id, move_status='completed', last_error=None)
            return json_response({
                'message': 'Source and target paths are identical. No movement required.',
                'output_path': source_path
            })

        # 标记移动进行中
        task_db.update_task(task_id, move_status='in_progress')

        try:
            # 确保目标目录存在
            target_dir = os.path.dirname(target_path)
            if target_dir:
                os.makedirs(target_dir, exist_ok=True)

            # 移动文件
            shutil.move(source_path, target_path)

            # 更新数据库
            task_db.update_task(
                task_id,
                output_path=target_path,
                target_path=target_path,
                move_status='completed',
                last_error=None
            )

            if global_logger:
                global_logger.info(f"Task {task_id} file moved: {source_path} -> {target_path}")

            # 如果启用了 Komga，触发媒体库扫描
            komga_toggle = current_app.config.get('KOMGA_TOGGLE', False)
            komga_library_id = current_app.config.get('KOMGA_LIBRARY_ID', '')
            if komga_toggle and komga_library_id:
                try:
                    from providers import komga
                    kmg = komga.KomgaAPI(
                        server=current_app.config['KOMGA_SERVER'],
                        username=current_app.config['KOMGA_USERNAME'],
                        password=current_app.config['KOMGA_PASSWORD'],
                        logger=global_logger
                    )
                    kmg.scan_library(komga_library_id)
                    if global_logger:
                        global_logger.info(f"Triggered Komga library scan after file move")
                except Exception as scan_err:
                    if global_logger:
                        global_logger.warning(f"Failed to trigger Komga scan: {scan_err}")

            return json_response({
                'message': 'File moved successfully',
                'output_path': target_path
            })

        except Exception as move_err:
            task_db.update_task(task_id, move_status='failed', last_error=str(move_err))
            raise move_err

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error moving task file {task_id}: {e}")
        return json_response({'error': f'Failed to move file: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/read-cbz', methods=['POST'])
def read_cbz_metadata(task_id):
    """从已完成的 CBZ 文件中重新读取并同步 ComicInfo.xml 元数据"""
    import os
    import zipfile
    import xml.etree.ElementTree as ET

    from database import task_db
    task_info = task_db.get_task(task_id)
    if not task_info:
        return json_response({'error': 'Task not found'}), 404

    cbz_path = task_info.get('output_path')
    if not cbz_path or not os.path.exists(cbz_path):
        return json_response({'error': '对应的物理压缩包文件不存在'}), 404

    comicinfo_dict = {}
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zf:
            if 'ComicInfo.xml' in zf.namelist():
                xml_content = zf.read('ComicInfo.xml')
                root = ET.fromstring(xml_content)
                for child in root:
                    # 获取标签名，处理可能有命名空间的情况
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if child.text:
                        comicinfo_dict[tag] = child.text
            else:
                return json_response({'error': '压缩包中未找到 ComicInfo.xml'}), 404
    except Exception as e:
        return json_response({'error': f'读取文件失败: {str(e)}'}), 500

    # 不更新数据库，只返回解析出的字典供前端比对
    return json_response({'comicinfo': comicinfo_dict})

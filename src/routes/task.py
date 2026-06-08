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
        
    if task_data.get('komga_id'):
        komga_server = app.config.get('KOMGA_SERVER', '').rstrip('/')
        if komga_server:
            task_data['komga_url'] = f"{komga_server}/book/{task_data['komga_id']}"
            
    return task_data


def extract_comicinfo_from_cbz(cbz_path):
    import os
    import zipfile
    import xml.etree.ElementTree as ET
    if not cbz_path or not os.path.exists(cbz_path):
        from flask import current_app
        logger = current_app.config.get('GLOBAL_LOGGER') if current_app else None
        if logger:
            logger.warning(f"extract_comicinfo_from_cbz failed: File not found or empty path: {cbz_path}")
        return None
    comicinfo_dict = {}
    try:
        with zipfile.ZipFile(cbz_path, 'r') as zf:
            comicinfo_name = next((name for name in zf.namelist() if name.lower() == 'comicinfo.xml'), None)
            if comicinfo_name:
                xml_content = zf.read(comicinfo_name)
                root = ET.fromstring(xml_content)
                
                # 定义标准字段映射，确保无论 XML 中大小写如何都能映射到标准名称
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
                
                for child in root:
                    tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                    if child.text:
                        standard_tag = key_map.get(tag.lower(), tag)
                        comicinfo_dict[standard_tag] = child.text
                return comicinfo_dict
    except Exception as e:
        from flask import current_app
        logger = current_app.config.get('GLOBAL_LOGGER') if current_app else None
        if logger:
            logger.error(f"extract_comicinfo_from_cbz error processing {cbz_path}: {e}")
        return None
    return None

def fetch_and_update_gmetadata_async(app, task_id, url):
    """后台任务：尝试获取 gmetadata 并更新任务"""
    with app.app_context():
        global_logger = app.config.get('GLOBAL_LOGGER')
        try:
            from database import task_db
            is_nhentai = 'nhentai.net' in url
            is_hitomi = 'hitomi.la' in url
            is_hdoujin = 'hdoujin.org' in url

            if is_nhentai:
                from providers import nhentai
                gallery_tool = nhentai.NHentaiTools(cookie=app.config.get('NHENTAI_COOKIE'), logger=global_logger)
            elif is_hitomi:
                from providers import hitomi
                gallery_tool = hitomi.HitomiTools(logger=global_logger)
            elif is_hdoujin:
                from providers import hdoujin
                gallery_tool = hdoujin.HDoujinTools(
                    session_token=app.config.get('HDOUJIN_SESSION_TOKEN'),
                    refresh_token=app.config.get('HDOUJIN_REFRESH_TOKEN'),
                    clearance_token=app.config.get('HDOUJIN_CLEARANCE_TOKEN'),
                    user_agent=app.config.get('HDOUJIN_USER_AGENT'),
                    logger=global_logger
                )
            else:
                gallery_tool = app.config.get('EH_TOOLS')
                if not gallery_tool:
                    return

            gmetadata = gallery_tool.get_gmetadata(url)
            if gmetadata:
                updates = {'metadata': gmetadata}
                
                # 下载封面
                raw_cover_url = gmetadata.get('thumb') or gmetadata.get('thumbnail_url')
                if raw_cover_url:
                    from utils import download_cover
                    cover_url = download_cover(raw_cover_url, task_id, app.config, global_logger)
                    updates['cover_url'] = cover_url
                
                # 检查 comicinfo 是否为空，如果为空，则根据 gmetadata 生成并打包
                task_info = task_db.get_task(task_id)
                if not task_info.get('comicinfo'):
                    try:
                        from main import prepare_metadata_and_path
                        from metadata_extractor import MetadataExtractor
                        from providers.ehtranslator import EhTagTranslator
                        
                        eh_translator = EhTagTranslator(enable_translation=app.config.get('TAGS_TRANSLATION', True))
                        extractor = MetadataExtractor(app.config, eh_translator)
                        parsed_meta = extractor.parse_gmetadata(gmetadata, logger=global_logger)
                        parsed_meta['Web'] = url.split('#')[0].split('?')[0]
                        
                        comicinfo_metadata, _ = prepare_metadata_and_path(parsed_meta, task_info.get('filename', ''), app, global_logger)
                        if comicinfo_metadata:
                            updates['comicinfo'] = comicinfo_metadata
                            
                            # 尝试打包进 CBZ
                            cbz_path = task_info.get('output_path')
                            if cbz_path:
                                import os
                                import cbztool
                                if os.path.exists(cbz_path):
                                    # 读取白名单配置
                                    comicinfo_config = app.config.get('COMICINFO', {}) or {}
                                    key_map = {
                                        'agerating': 'AgeRating', 'languageiso': 'LanguageISO',
                                        'alternateseries': 'AlternateSeries', 'alternatenumber': 'AlternateNumber',
                                        'storyarc': 'StoryArc', 'storyarcnumber': 'StoryArcNumber',
                                        'seriesgroup': 'SeriesGroup', 'coverartist': 'CoverArtist',
                                        'gtin': 'GTIN', 'number': 'Number', 'series': 'Series',
                                        'title': 'Title', 'writer': 'Writer', 'penciller': 'Penciller',
                                        'translator': 'Translator', 'tags': 'Tags', 'web': 'Web',
                                        'manga': 'Manga', 'genre': 'Genre'
                                    }
                                    allowed_keys = set()
                                    for k in comicinfo_config.keys():
                                        allowed_keys.add(key_map.get(k.lower(), k.capitalize()))
                                        
                                    filtered_metadata = {k: v for k, v in comicinfo_metadata.items() if k in allowed_keys}
                                    cbztool.update_comicinfo_in_cbz(cbz_path, filtered_metadata, logger=global_logger)
                    except Exception as meta_err:
                        if global_logger:
                            global_logger.warning(f"后台自动生成/打包 comicinfo 失败 (task_id: {task_id}): {meta_err}")

                task_db.update_task(task_id, **updates)
                if global_logger:
                    global_logger.info(f"后台异步获取 gmetadata 并处理封面/元数据成功 (task_id: {task_id})")
        except Exception as e:
            if global_logger:
                global_logger.warning(f"后台异步获取 gmetadata 失败 (task_id: {task_id}): {e}")

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
        search_query = request.args.get('search', '').strip()
        
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

        sort_by = request.args.get('sort', 'created_at')
        if sort_by not in ['created_at', 'updated_at', 'id']:
            sort_by = 'created_at'

        order_by_sql = f"{sort_by} DESC"

        # 从数据库获取任务列表
        db_tasks, total = task_db.get_tasks(status_filter, search_query if search_query else None, page, page_size, order_by=order_by_sql)

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

        # 兜底内存排序
        if sort_by == 'updated_at':
            db_tasks.sort(key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)
        else:
            db_tasks.sort(key=lambda x: x.get('id', ''), reverse=True)

        # 获取各个状态的任务数量统计
        # 如果存在搜索条件，则状态统计也应该基于搜索条件过滤
        try:
            with sqlite3.connect('./data/tasks.db') as conn:
                conn.row_factory = sqlite3.Row
                
                where_clauses = []
                params = []
                if search_query:
                    import re
                    terms = [t.strip() for t in re.split(r'[,|\n]+', search_query) if t.strip()]
                    if terms:
                        term_clauses = []
                        for term in terms:
                            term_clauses.append("(id LIKE ? OR filename LIKE ? OR url LIKE ?)")
                            search_term = f"%{term}%"
                            params.extend([search_term, search_term, search_term])
                        where_clauses.append("(" + " OR ".join(term_clauses) + ")")
                
                where_clause = ""
                if where_clauses:
                    where_clause = "WHERE " + " AND ".join(where_clauses)

                cursor = conn.execute(f'''
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM tasks
                    {where_clause}
                    GROUP BY status
                ''', params)
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

@bp.route('/api/tasks/movable', methods=['GET'])
def get_movable_tasks():
    """获取所有具有可移动归档路径差异的已完成任务"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        from utils import TaskStatus
        
        # 获取所有完成的任务 (传入 page=1, page_size=99999)
        db_tasks, _ = task_db.get_tasks(status_filter=TaskStatus.COMPLETED, search_query=None, page=1, page_size=99999)
        
        movable_tasks = []
        for db_task in db_tasks:
            enriched = enrich_task_data(db_task, current_app)
            if enriched.get('has_path_difference'):
                # 提取精简所需的信息
                movable_tasks.append({
                    'id': enriched['id'],
                    'filename': enriched.get('filename', '未知文件名'),
                    'current_path': enriched.get('output_path'),
                    'target_path': enriched.get('target_path'),
                    'cover_url': enriched.get('cover_url')
                })
                
        return json_response({'movable_tasks': movable_tasks})
        
    except Exception as e:
        if global_logger:
            global_logger.error(f"Error getting movable tasks: {e}")
        return json_response({'error': f'Failed to get movable tasks: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/refresh-gmetadata', methods=['POST'])
def refresh_task_gmetadata(task_id):
    """从网络重新获取最新的 gmetadata.json"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404
            
        url = task_info.get('url')
        if not url:
            return json_response({'error': 'Task has no url'}), 400
            
        is_nhentai = 'nhentai.net' in url
        is_hitomi = 'hitomi.la' in url
        is_hdoujin = 'hdoujin.org' in url

        if is_nhentai:
            from providers import nhentai
            gallery_tool = nhentai.NHentaiTools(cookie=current_app.config.get('NHENTAI_COOKIE'), logger=global_logger)
        elif is_hitomi:
            from providers import hitomi
            gallery_tool = hitomi.HitomiTools(logger=global_logger)
        elif is_hdoujin:
            from providers import hdoujin
            gallery_tool = hdoujin.HDoujinTools(
                session_token=current_app.config.get('HDOUJIN_SESSION_TOKEN'),
                refresh_token=current_app.config.get('HDOUJIN_REFRESH_TOKEN'),
                clearance_token=current_app.config.get('HDOUJIN_CLEARANCE_TOKEN'),
                user_agent=current_app.config.get('HDOUJIN_USER_AGENT'),
                logger=global_logger
            )
        else:
            gallery_tool = current_app.config.get('EH_TOOLS')
            if not gallery_tool:
                 return json_response({'error': 'EH_TOOLS not initialized'}), 500

        gmetadata = gallery_tool.get_gmetadata(url)
        if not gmetadata:
             return json_response({'error': 'Failed to get gmetadata from network'}), 500
             
        updates = {'metadata': gmetadata}
        raw_cover_url = gmetadata.get('thumb') or gmetadata.get('thumbnail_url')
        if raw_cover_url:
            from utils import download_cover
            cover_url = download_cover(raw_cover_url, task_id, current_app.config, global_logger)
            updates['cover_url'] = cover_url
            
        task_db.update_task(task_id, **updates)
        
        updated_task = task_db.get_task(task_id)
        return json_response({'message': 'gmetadata refreshed and cover updated successfully', 'task': enrich_task_data(updated_task, current_app)})
        
    except Exception as e:
        if global_logger:
            global_logger.error(f"Error refreshing gmetadata for task {task_id}: {e}")
        return json_response({'error': f'Failed to refresh gmetadata: {str(e)}'}), 500

@bp.route('/api/tasks/<task_id>/generate-comicinfo', methods=['GET'])
def generate_comicinfo_from_metadata(task_id):
    """从数据库的原始 metadata（gmetadata）通过格式化和模板渲染生成 comicinfo"""
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        from database import task_db
        from main import prepare_metadata_and_path
        from metadata_extractor import MetadataExtractor
        from providers.ehtranslator import EhTagTranslator

        task_info = task_db.get_task(task_id)
        if not task_info:
            return json_response({'error': 'Task not found'}), 404

        gmetadata = task_info.get('metadata')
        if not gmetadata:
            return json_response({'error': 'No original metadata available for this task'}), 400

        url = task_info.get('url', '')
        filename = task_info.get('filename', '')

        # 1. 经过 metadata_extractor 格式化一遍
        eh_translator = EhTagTranslator(enable_translation=current_app.config.get('TAGS_TRANSLATION', True))
        extractor = MetadataExtractor(current_app.config, eh_translator)
        metadata = extractor.parse_gmetadata(gmetadata, logger=global_logger)
        
        # 2. 补充 Web 字段
        metadata['Web'] = url.split('#')[0].split('?')[0]

        # 3. 根据 prepare_metadata_and_path 中的自定义模板功能渲染成最终的 comicinfo
        comicinfo_metadata, _ = prepare_metadata_and_path(metadata, filename, current_app, global_logger)

        if not comicinfo_metadata:
            comicinfo_metadata = {}

        return json_response({
            'message': 'Successfully generated comicinfo from original metadata',
            'comicinfo': comicinfo_metadata
        })

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error generating comicinfo for task {task_id}: {e}")
        return json_response({'error': f'Failed to generate comicinfo: {str(e)}'}), 500

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
            
        # 移除之前的 SourceURL 逻辑，使用更符合 ComicInfo 规范的 Web 字段

        # 定义所有支持的 ComicInfo 标准字段
        key_map = {
            'agerating': 'AgeRating', 'languageiso': 'LanguageISO',
            'alternateseries': 'AlternateSeries', 'alternatenumber': 'AlternateNumber',
            'storyarc': 'StoryArc', 'storyarcnumber': 'StoryArcNumber',
            'seriesgroup': 'SeriesGroup', 'coverartist': 'CoverArtist',
            'gtin': 'GTIN', 'number': 'Number', 'series': 'Series',
            'title': 'Title', 'writer': 'Writer', 'penciller': 'Penciller',
            'translator': 'Translator', 'tags': 'Tags', 'web': 'Web',
            'manga': 'Manga', 'genre': 'Genre', 'summary': 'Summary',
            'publisher': 'Publisher'
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
        
        # 性能优化：如果数据有差异，或者上一次打包状态是失败/待处理（比如之前文件丢失现在修复了），则强制执行打包
        needs_repack = bool(pending_changes_diff) or task_info.get('repack_status') in ['failed', 'pending']

        if needs_repack and cbz_path and os.path.exists(cbz_path):
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
        elif needs_repack and cbz_path:
            # 有 output_path 但文件不存在，此时无法打包
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

        # 处理 Web 字段：如果 Web 填入了一个我们支持的源站 URL（如 EH, NH, HDoujin），更新任务 url 并自动触发元数据抓取
        web_url = data.get('Web')
        if web_url:
            web_url_str = str(web_url).strip()
            # ComicInfo 规范允许 Web 字段包含多个由空格分隔的 URL
            if web_url_str:
                urls = web_url_str.split()
                matched_url = None
                for u in urls:
                    _, site_type = task_db.normalize_url(u)
                    if site_type != 'other':
                        matched_url = u
                        break
                
                if matched_url and matched_url != task_info.get('url'):
                    # 更新任务 URL 为实际用于刮削的有效链接
                    task_db.update_task(task_id, url=matched_url)
                    # 触发异步抓取流程
                    import main
                    executor = main.executor
                    if executor:
                        app = current_app._get_current_object()
                        executor.submit(fetch_and_update_gmetadata_async, app, task_id, matched_url)

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
            'genre': 'Genre',
            'publisher': 'Publisher'
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
    from database import task_db
    task_info = task_db.get_task(task_id)
    if not task_info:
        return json_response({'error': 'Task not found'}), 404

    cbz_path = task_info.get('output_path')
    if not cbz_path or not os.path.exists(cbz_path):
        return json_response({'error': '对应的物理压缩包文件不存在'}), 404

    comicinfo_dict = extract_comicinfo_from_cbz(cbz_path)
    if comicinfo_dict is None:
        return json_response({'error': '读取文件失败或压缩包中未找到 ComicInfo.xml'}), 404

    # 保护可能由 Komga 等渠道注入的后备补充数据
    # 如果压缩包内确实缺少这些字段，但数据库里已经补充过了，就保留数据库里的值，防止被洗掉
    existing_comicinfo = task_info.get('comicinfo') or {}
    for k in ['Series', 'Title', 'Number', 'Web']:
        if not comicinfo_dict.get(k) and existing_comicinfo.get(k):
            comicinfo_dict[k] = existing_comicinfo.get(k)

    # 读取cbz的内容后将数据更新到comicinfo字段
    task_db.update_task(task_id, comicinfo=comicinfo_dict)

    updated_task = task_db.get_task(task_id)
    return json_response({
        'message': '读取成功并已更新元数据',
        'comicinfo': comicinfo_dict,
        'task': enrich_task_data(updated_task, current_app)
    })

@bp.route('/api/tasks/sync-komga', methods=['POST'])
def sync_komga_task():
    global_logger = current_app.config.get('GLOBAL_LOGGER')
    try:
        data = request.get_json() or {}
        url = data.get('url')
        if not url:
            return json_response({'error': 'No URL provided'}), 400

        from database import task_db
        from providers import komga
        from datetime import datetime, timezone
        from utils import TaskStatus

        kmg = komga.KomgaAPI(
            server=current_app.config['KOMGA_SERVER'],
            username=current_app.config['KOMGA_USERNAME'],
            password=current_app.config['KOMGA_PASSWORD'],
            logger=global_logger
        )

        def process_single_komga_book(book_data, provided_url):
            import time
            komga_path = book_data.get('url')
            
            # 应用路径映射 KOMGA_PATH_MAPPING
            path_mapping = current_app.config.get('KOMGA_PATH_MAPPING') or {}
            if isinstance(path_mapping, dict) and komga_path:
                for k_path, ha_path in path_mapping.items():
                    if komga_path.startswith(k_path):
                        komga_path = komga_path.replace(k_path, ha_path, 1)
                        break
            
            book_name = book_data.get('name')
            komga_series_title = book_data.get('seriesTitle')
            is_oneshot = book_data.get('oneshot', False)
            links = book_data.get('metadata', {}).get('links', [])

            matched_task = None
            source_url = None
            
            # 提取所有有效链接
            all_urls = []

            for link in links:
                l_url = link.get('url')
                if l_url:
                    if l_url not in all_urls:
                        all_urls.append(l_url)
                    if not source_url:
                        source_url = l_url
                    normalized_url, _ = task_db.normalize_url(l_url)
                    task = task_db.get_task_by_normalized_url(normalized_url)
                    if task and not matched_task:
                        matched_task = task
                        source_url = l_url
            
            # 移除退而求其次使用 provided_url 的逻辑，因为 provided_url 可能是系列链接
            # source_url 将保持 None 如果 metadata.links 中没有外部链接
            
            komga_id = book_data.get('id')
            
            if matched_task:
                task_id = matched_task['id']
                current_path = matched_task.get('output_path')
                target_path = matched_task.get('target_path')
                
                updates = {}
                if current_path != komga_path:
                    updates['output_path'] = komga_path
                if target_path != komga_path:
                    updates['target_path'] = komga_path
                    
                # 只要触发了重新同步，就主动清除历史错误记录
                if matched_task.get('last_error'):
                    updates['last_error'] = None
                    
                if komga_id and matched_task.get('komga_id') != komga_id:
                    updates['komga_id'] = komga_id
                    
                # 注入 Series、Title、Number 和 Web
                current_comicinfo = matched_task.get('comicinfo') or {}
                comicinfo_modified = False
                
                # 如果已存在的任务没有 comicinfo，则尝试直接从物理文件中提取兜底
                if not current_comicinfo:
                    extracted = extract_comicinfo_from_cbz(komga_path)
                    if extracted:
                        current_comicinfo = extracted
                        comicinfo_modified = True
                
                if not is_oneshot and komga_series_title:
                    if not current_comicinfo.get('Series'):
                        current_comicinfo['Series'] = komga_series_title
                        comicinfo_modified = True
                        
                if not current_comicinfo.get('Title') and book_name:
                    current_comicinfo['Title'] = book_name
                    comicinfo_modified = True
                    
                komga_number = book_data.get('number')
                if not current_comicinfo.get('Number') and komga_number:
                    current_comicinfo['Number'] = str(komga_number)
                    comicinfo_modified = True
                        
                if all_urls:
                    if not current_comicinfo.get('Web'):
                        current_comicinfo['Web'] = " ".join(all_urls)
                        comicinfo_modified = True
                        
                if comicinfo_modified:
                    updates['comicinfo'] = current_comicinfo
                        
                if updates:
                    task_db.update_task(task_id, **updates)

                # 检查旧任务是否缺失元数据，如果缺失，就像新任务一样触发一次元数据获取管线
                # 注意：只要触发了元数据管线，最后写入时也会用数据库的 comicinfo（包含了这里注入的 Series）兜底，所以没冲突
                needs_metadata = not matched_task.get('gmetadata') or not matched_task.get('comicinfo')
                if needs_metadata:
                    import main
                    executor = main.executor
                    if executor:
                        app = current_app._get_current_object()
                        executor.submit(fetch_and_update_gmetadata_async, app, task_id, source_url)

                return task_id, bool(updates), needs_metadata, matched_task
            else:
                import time
                time.sleep(0.001) # 防止批量生成ID冲突
                task_id = datetime.now(timezone.utc).strftime('%y%m%d%H%M%S%f')
                task_db.add_task(
                    task_id, 
                    status=TaskStatus.COMPLETED, 
                    mode="no-download", 
                    output_path=komga_path, 
                    target_path=komga_path,
                    filename=book_name,
                    url=source_url,
                    komga_id=komga_id
                )
                
                comicinfo_dict = extract_comicinfo_from_cbz(komga_path) or {}
                
                # 注入 Series、Title、Number 和 Web
                comicinfo_modified = False
                if not is_oneshot and komga_series_title:
                    if not comicinfo_dict.get('Series'):
                        comicinfo_dict['Series'] = komga_series_title
                        comicinfo_modified = True
                    
                if not comicinfo_dict.get('Title') and book_name:
                    comicinfo_dict['Title'] = book_name
                    comicinfo_modified = True
                    
                komga_number = book_data.get('number')
                if not comicinfo_dict.get('Number') and komga_number:
                    comicinfo_dict['Number'] = str(komga_number)
                    comicinfo_modified = True
                    
                if all_urls:
                    if not comicinfo_dict.get('Web'):
                        comicinfo_dict['Web'] = " ".join(all_urls)
                        comicinfo_modified = True
                    
                if comicinfo_dict:
                    task_db.update_task(task_id, comicinfo=comicinfo_dict)
                
                executor = current_app.config.get('EXECUTOR')
                if executor:
                    app = current_app._get_current_object()
                    executor.submit(fetch_and_update_gmetadata_async, app, task_id, source_url)
                
                return task_id, True, True, None

        # 检查是否是系列导入
        is_series = '/series/' in url.lower()
        if is_series:
            from urllib.parse import urlparse
            parsed_url = urlparse(url)
            series_id = parsed_url.path.strip('/').split('/')[-1]
            
            response = kmg.session.get(f"{kmg.server}/api/v1/series/{series_id}/books?unpaged=true")
            if response.status_code != 200:
                return json_response({'error': f'Failed to get series books from Komga: {response.text}'}), 400
            
            books_data = response.json().get('content', [])
            if not books_data:
                return json_response({'error': 'No books found in this series'}), 404
            
            processed = 0
            task_ids = []
            for book_data in books_data:
                task_id, _, _, _ = process_single_komga_book(book_data, url)
                task_ids.append(str(task_id))
                processed += 1
                
            return json_response({
                'message': f'成功批量同步了 {processed} 本书籍', 
                'count': processed, 
                'task_id': ",".join(task_ids), 
                'updated': True
            })
        else:
            # 单本书导入 (book or oneshot)
            response = kmg.get_book(url)
            if response.status_code != 200:
                return json_response({'error': f'Failed to get book from Komga: {response.text}'}), 400
            
            book_data = response.json()
            task_id, updated, needs_metadata, matched_task = process_single_komga_book(book_data, url)
            
            if matched_task:
                if updated or needs_metadata:
                    msg = 'Task paths updated and errors cleared successfully' if updated else 'Task paths are up-to-date'
                    if needs_metadata:
                        msg += ', metadata fetch started'
                    return json_response({'message': msg, 'task_id': task_id, 'updated': True})
                else:
                    return json_response({'message': 'Task paths are already up-to-date and metadata exists', 'task_id': task_id, 'updated': False})
            else:
                updated_task = task_db.get_task(task_id)
                return json_response({'message': 'New task created from Komga', 'task_id': task_id, 'task': enrich_task_data(updated_task, current_app)})

    except Exception as e:
        if global_logger:
            global_logger.error(f"Error syncing Komga task: {e}")
        return json_response({'error': f'Failed to sync task: {str(e)}'}), 500


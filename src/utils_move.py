# src/utils_move.py
import os
import jinja2

def calculate_task_move_path(task_info, app, logger=None):
    """
    根据任务的元数据及配置中的 MOVE_PATH 模板渲染建议的目标物理路径。
    
    Args:
        task_info: 任务字典，包含 comicinfo/metadata 以及 output_path
        app: Flask app 实例，用于读取配置
        logger: 可选日志对象
    
    Returns:
        渲染后的绝对物理路径，若不可移动或渲染失败则返回 None
    """
    move_path_template = app.config.get('MOVE_PATH')
    if not move_path_template:
        if logger:
            logger.info("未配置完成后移动的路径 (MOVE_PATH)，无法自动计算。")
        return None
        
    output_path = task_info.get('output_path')
    if not output_path:
        if logger:
            logger.warning("任务没有 output_path，无法计算移动目标路径。")
        return None

    filename = os.path.basename(output_path)
    
    # 结合 comicinfo 和 metadata，优先 comicinfo
    metadata = {}
    if task_info.get('metadata'):
        metadata.update(task_info.get('metadata'))
    if task_info.get('comicinfo'):
        metadata.update(task_info.get('comicinfo'))
        
    # 准备模板变量：统一转为小写以保持模板兼容性
    template_vars = {k.lower(): v for k, v in metadata.items()}
    # 保留原驼峰键以兼容有些手写模板
    for k, v in metadata.items():
        template_vars[k] = v
        
    template_vars['filename'] = filename
    
    # 根据可能已修改的 penciller 和 writer 更新 author
    template_vars['author'] = template_vars.get('penciller') or template_vars.get('writer') or None
    # 优先将 comicinfo 里的 Series 作为物理 series 变量使用
    template_vars['series'] = metadata.get('Series') or None

    # 计算 author 限制，防止路径过长（根据 Tags 里是否包含 anthology）
    tags = metadata.get('Tags', '')
    if isinstance(tags, list):
        tags = ', '.join(tags)
    tags = str(tags).lower()
    limit = 2 if 'anthology' in [tag.strip() for tag in tags.split(',')] else 3

    for key in ('penciller', 'writer'):
        value = template_vars.get(key)
        if value and isinstance(value, str) and len([item for item in value.split(',') if item.strip()]) >= limit:
            template_vars[key] = 'anthology'

    # 定义模板渲染环境
    class UnknownUndefined(jinja2.Undefined):
        def __str__(self):
            return 'Unknown'
            
    def finalize_for_path(value):
        return value if value else 'Unknown'

    jinja_env_for_path = jinja2.Environment(
        undefined=UnknownUndefined,
        finalize=finalize_for_path
    )
    
    try:
        path_template = jinja_env_for_path.from_string(move_path_template)
        move_file_path = path_template.render(template_vars)
        if not move_file_path:
            return None
            
        # 规范化文件名拼接
        template_has_filename = '{{filename}}' in move_path_template
        if template_has_filename:
            if not os.path.splitext(move_file_path)[1].lower() in ['.7z', '.zip', '.cbz']:
                move_file_path += '.cbz'
        else:
            move_file_path = os.path.join(move_file_path, filename)
            
        # 返回规范后的绝对路径
        return os.path.abspath(move_file_path)
    except Exception as e:
        if logger:
            logger.error(f"渲染移动路径模板失败: {e}")
        return None

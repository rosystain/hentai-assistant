import zipfile, os
import shutil
import tempfile
from xml.dom.minidom import parseString
import dicttoxml
from utils import check_dirs
from PIL import Image
from natsort import natsorted
import detectAd
import re

# 广告文件名正则列表
ad_file_pattern = re.compile(
    r'('
    r'^zzz.*\.(jpg|png|webp)$|'        # 以 zzz 开头的图片
    r'^YZv5\.0\.png$|'                 # 固定文件名
    r'脸肿汉化组招募|'                  # 含有中文关键字
    r'.*_ZZZZ0.*\..*$|'                # _ZZZZ0
    r'.*_ZZZZ1.*\..*$|'                # _ZZZZ1
    r'.*_zzz.*\..*$|'                  # 任意 _zzz
    r'無邪気漢化組招募圖_ver.*\.png$|' # 無邪気汉化组招募图
    r'無邪気無修宇宙分組_ver.*\.png$|' # 無邪気无修宇宙分组
    r'^_.+\.jpg$'                      # 以 _ 开头的 jpg
    r')',
    re.IGNORECASE
)

def make_comicinfo_xml(metadata):
    return parseString(
        dicttoxml.dicttoxml(metadata, custom_root='ComicInfo', attr_type=False)
    ).toprettyxml(indent="  ", encoding="UTF-8")

def write_xml_to_zip(file_path, mapped_file_path, metadata, app=None, logger=None):
    zip_file_root = os.path.dirname(file_path)
    zip_file_name = os.path.basename(file_path)
    copy = app and app.config.get('keep_original_file', False)
    remove_ad_flag = app and app.config.get('remove_ads', False)

    print(f"处理文件: {file_path}, 复制原文件: {copy}, 删除广告页: {remove_ad_flag}")
    if logger:
        logger.info(f"处理文件: {file_path}, 复制原文件: {copy}, 删除广告页: {remove_ad_flag}")

    xml_content = make_comicinfo_xml(metadata)

    # 检查输入是文件夹还是ZIP文件
    if os.path.isdir(file_path):
        # 处理文件夹输入
        # 获取所有图片并自然排序
        img_files = []
        for root, dirs, files in os.walk(file_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.jxl')):
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, file_path)
                    img_files.append(rel_path)
        img_files = natsorted(img_files, key=lambda name: os.path.basename(name))
    else:
        # 处理ZIP文件输入
        # 获取所有图片并自然排序
        with zipfile.ZipFile(file_path, 'r') as src_zip:
            img_files = [f for f in src_zip.namelist() if f.lower().endswith(
                ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.avif', '.jxl')
            )]
        img_files = natsorted(img_files, key=lambda name: os.path.basename(name))

    if not img_files:
        msg = f"文件夹 {file_path} 内没有找到有效图片"
        if logger:
            logger.warning(msg)
        else:
            print(msg)
        return None

    # 广告页检测
    ad_pages = set()
    if remove_ad_flag:
        if logger:
            logger.info("正在检测广告页...")
        start_idx = max(0, len(img_files) - 10)
        normal_num = 0
        for i in range(len(img_files) - 1, start_idx - 1, -1):
            if i in ad_pages:
                continue
            name = img_files[i]
            basename = os.path.basename(name)
            # 文件名匹配
            if ad_file_pattern.search(basename):
                ad_pages.add(i)
                (logger.debug if logger else print)(f"[DEBUG] 文件名匹配广告: {i} => {basename}")
                continue
            # 图像检测
            try:
                if os.path.isdir(file_path):
                    # 从文件夹读取图片
                    img_path = os.path.join(file_path, name)
                    with Image.open(img_path) as img:
                        img.load()
                        is_ad = detectAd.is_ad_img(img, logger)
                        if is_ad:
                            ad_pages.add(i)
                            (logger.debug if logger else print)(f"[DEBUG] 二维码检测广告: {i} => {name}")
                        elif normal_num > 2:
                            break
                        else:
                            normal_num += 1
                else:
                    # 从ZIP文件读取图片
                    with zipfile.ZipFile(file_path, 'r') as src_zip, src_zip.open(name) as f, Image.open(f) as img:
                        img.load()
                        is_ad = detectAd.is_ad_img(img, logger)
                        if is_ad:
                            ad_pages.add(i)
                            (logger.debug if logger else print)(f"[DEBUG] 二维码检测广告: {i} => {name}")
                        elif normal_num > 2:
                            break
                        else:
                            normal_num += 1
            except Exception as e:
                (logger.debug if logger else print)(f"[DEBUG] 打开图片 {name} 异常: {e}")
                continue

        # 邻页补充
        if ad_pages:
            start_idx = min(ad_pages)
            ad_num = 0
            for i in range(start_idx, len(img_files)):
                if i in ad_pages:
                    ad_num += 1
                    continue
                if ad_num >= 2 or ((i - 1 in ad_pages) and (i + 1 in ad_pages)):
                    ad_pages.add(i)
                    (logger.debug if logger else print)(f"[DEBUG] 根据邻页规则补充广告: {i} => {img_files[i]}")
                else:
                    ad_num = 0
            if logger:
                logger.info(f"[INFO] 最终广告页索引: {sorted(ad_pages)}")
                logger.info(f"[INFO] 最终广告页文件: {', '.join([img_files[i] for i in sorted(ad_pages)])}")
            else:
                print(f"[INFO] 最终广告页索引: {sorted(ad_pages)}")
                print(f"[INFO] 最终广告页文件: {', '.join([img_files[i] for i in sorted(ad_pages)])}")

    # 安全临时文件（唯一文件名，避免冲突）
    with tempfile.NamedTemporaryFile(dir=zip_file_root, suffix=".cbz", delete=False) as tmp:
        target_zip_path = tmp.name

    # 创建目标ZIP文件并写入内容
    with zipfile.ZipFile(target_zip_path, 'w', zipfile.ZIP_DEFLATED) as tgt_zip:
        # 写入非广告页（流式复制，节省内存）
        for idx, name in enumerate(img_files):
            if idx in ad_pages:
                continue
            if os.path.isdir(file_path):
                # 从文件夹复制文件
                src_path = os.path.join(file_path, name)
                with open(src_path, 'rb') as source, tgt_zip.open(name, 'w') as target:
                    shutil.copyfileobj(source, target)
            else:
                # 从ZIP文件复制
                with zipfile.ZipFile(file_path, 'r') as src_zip, src_zip.open(name) as source, tgt_zip.open(name, 'w') as target:
                    shutil.copyfileobj(source, target)

        # 写入 ComicInfo.xml
        tgt_zip.writestr("ComicInfo.xml", xml_content)

    # 文件替换逻辑
    if copy:
        try:
            if os.path.isdir(file_path):
                # 对于文件夹，移动到Completed目录
                completed_path = os.path.join(zip_file_root, 'Completed')
                shutil.move(file_path, os.path.join(check_dirs(completed_path), zip_file_name))
            else:
                # 对于ZIP文件，使用原有逻辑
                completed_path = os.path.join(zip_file_root, 'Completed')
                os.renames(file_path, os.path.join(check_dirs(completed_path), zip_file_name))
        except Exception as e:
            if logger:
                logger.error(e)

    else:
        try:
            if os.path.isdir(file_path):
                # 对于文件夹，删除整个目录
                shutil.rmtree(file_path)
            else:
                # 对于ZIP文件，删除文件
                os.remove(file_path)
        except Exception as e:
            if logger:
                logger.error(e)

    new_file_path = os.path.splitext(file_path)[0] + ".cbz"
    shutil.move(target_zip_path, new_file_path)

    # 移动到映射目录
    mapped_file_path = os.path.splitext(mapped_file_path)[0] + '.cbz'
    if mapped_file_path != new_file_path:
        os.makedirs(os.path.dirname(mapped_file_path), exist_ok=True)
        shutil.move(new_file_path, mapped_file_path)
        (logger.info if logger else print)(f"文件移动到映射目录: {mapped_file_path}")
        return mapped_file_path

    return new_file_path

# src/config.py
import yaml
import os
import logging
import sqlite3
from datetime import datetime, timezone

from providers import komga, aria2, ehentai, nhentai, hdoujin
from utils import TaskStatus

# 定义配置文件的路径
CONFIG_DIR = 'data'
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.yaml')

def get_default_config():
    return {
        'general': {
            'keep_torrents': 'false',
            'keep_original_file': 'false',
            'prefer_japanese_title': 'true',
            'move_path': ''
        },
        'advanced':{
            'tags_translation': 'false',
            'remove_ads': 'false',
            'aggressive_series_detection': 'false', # 启用后，E-Hentai 会对 AltnateSeries 字段进行更激进的检测。
            'openai_series_detection': 'false', # 启用后，使用配置号的 OpenAI 接口对标题进行系列名和序号的检测。
            'prefer_openai_series': 'false' # 启用后，优先使用 OpenAI 进行系列识别，正则作为后备方案。
        },
        'ehentai': {
            'ipb_member_id': '',
            'ipb_pass_hash': '',
            'favorite_sync': 'false',
            'favorite_sync_interval': '6h',
            'favcat_whitelist': [],
            'initial_scan_pages': 1,
            'auto_download_favorites': 'false',
            'hath_check_enabled': 'false',
            'hath_check_interval': '30m'
        },
        'nhentai': {
            'cookie': ''
        },
        'hdoujin': {
            'session_token': '',
            'refresh_token': '',
            'clearance_token': '',
            'user_agent': '' # 请在此处填入您获取 clearance_token 时使用的浏览器的 User-Agent
        },
        'aria2': {
            'enable': 'false',
            'server': 'http://localhost:6800/jsonrpc',
            'token': '',
            'download_dir': '',
            'mapped_dir': ''
        },
        'komga': {
            'enable': 'false',
            'server': '',
            'username': '',
            'password': '',
            'library_id': '',
            'index_sync': 'false',
            'index_sync_interval': '6h'
        },
        'notification': {},
        'openai': {
            'api_key': '',
            'base_url': '',
            'model': ''
        },
        'comicinfo': {
            'title': '{{title}}',
            'writer': '{{writer}}',
            'penciller': '{{penciller}}',
            'translator': '{{translator}}',
            'tags': '{{tags}}',
            'web': '{{web}}',
            'agerating': '{{agerating}}',
            'manga': '{{manga}}',
            'genre': '{{genre}}',
            'languageiso': '{{languageiso}}',
            'number': '',
            'alternateseries': '{{series}}',
            'alternatenumber': '{{number}}'
        }
    }

def save_config(config_data):
    # 将配置数据保存到 config.yaml 文件
    os.makedirs(CONFIG_DIR, exist_ok=True)
    config_to_save = {k: v for k, v in config_data.items() if k != 'status'}

    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as configfile:
            # 逐个 section 写入，并在它们之间添加空行以提高可读性
            for i, (section, data) in enumerate(config_to_save.items()):
                if i > 0:
                    configfile.write('\n')
                yaml.dump({section: data}, configfile, allow_unicode=True, sort_keys=False)
    except Exception as e:
        print(f"Error saving config file: {e}")
        raise

def lowercase_keys(obj):
    if isinstance(obj, dict):
        return {k.lower(): lowercase_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [lowercase_keys(elem) for elem in obj]
    return obj

def deep_merge_dicts(source, defaults):
    """
    Recursively merges a `source` dictionary into a `defaults` dictionary.
    - If a key from `defaults` is missing in `source`, it's added.
    - If values are dictionaries, they are merged recursively.
    - `source` values take precedence.
    - Returns the merged dictionary and a boolean indicating if changes were made.
    """
    updated = False
    merged = defaults.copy()

    for key, default_value in defaults.items():
        if key not in source:
            updated = True
            continue  # Keep the default value, no need to assign merged[key] = default_value

        source_value = source[key]
        
        # If both values are dictionaries, recurse
        if isinstance(default_value, dict) and isinstance(source_value, dict):
            merged[key], sub_updated = deep_merge_dicts(source_value, default_value)
            if sub_updated:
                updated = True
        # Otherwise, use the source value, but check if it's different from default
        # This handles cases where user has a value, but we might want to ensure it is the right type later
        else:
            merged[key] = source_value

    # Also, add keys from source that are not in defaults (e.g., user-defined notifiers)
    for key, source_value in source.items():
        if key not in defaults:
            merged[key] = source_value
            # This is not considered an 'update' in the sense of adding missing defaults
            
    return merged, updated


def load_config():
    # 加载 config.yaml 文件，如果不存在则创建并使用默认值
    default_config = get_default_config()
    
    if not os.path.exists(CONFIG_PATH):
        print(f"'{CONFIG_PATH}' not found. Creating a new one with default settings.")
        save_config(default_config)
        return default_config
    
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as configfile:
            user_config_raw = yaml.safe_load(configfile) or {}
        if not isinstance(user_config_raw, dict):
            raise ValueError("Config file is not a valid dictionary.")
        user_config = lowercase_keys(user_config_raw)
    except Exception as e:
        print(f"Error reading or parsing config file '{CONFIG_PATH}', using default config: {e}")
        return default_config

    # Deep merge user config with defaults
    config_data, config_updated = deep_merge_dicts(user_config, default_config)

    # Special handling for the notification section to ensure each notifier has default fields
    if 'notification' in config_data and isinstance(config_data['notification'], dict):
        for notifier_key, notifier_details in config_data['notification'].items():
            if isinstance(notifier_details, dict):
                if 'enable' not in notifier_details:
                    notifier_details['enable'] = False  # Default to disabled
                    config_updated = True
                if 'name' not in notifier_details:
                    notifier_details['name'] = notifier_key # Default name to its key
                    config_updated = True

    # If any missing keys were added, save the updated config back to the file
    if config_updated:
        print(f"Config file '{CONFIG_PATH}' has been updated with missing default entries.")
        save_config(config_data)
        
    # --- Type Conversion (from string to boolean, etc.) ---
    # This should happen *after* loading and merging, before returning.
    
    TRUE_VALUES = {'true', 'yes', 'on', '1', True}
    FALSE_VALUES = {'false', 'no', 'off', '0', False}

    # Create a new dictionary for the converted data to avoid modifying during iteration
    converted_config = {}
    for section, section_items in config_data.items():
        if not isinstance(section_items, dict):
            converted_config[section] = section_items
            continue
        
        converted_section = {}
        for key, value in section_items.items():
            # 跳过特定的数值字段，不进行布尔转换
            if section == 'ehentai' and key == 'initial_scan_pages':
                # 保持为整数
                try:
                    converted_section[key] = int(value)
                except (ValueError, TypeError):
                    converted_section[key] = 1  # 默认值
            elif isinstance(value, str):
                lower_value = value.lower()
                if lower_value in TRUE_VALUES:
                    converted_section[key] = True
                elif lower_value in FALSE_VALUES:
                    converted_section[key] = False
                else:
                    converted_section[key] = value
            else: # if not a string
                converted_section[key] = value
        converted_config[section] = converted_section

    return converted_config
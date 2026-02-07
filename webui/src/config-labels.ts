/**
 * 配置字段的中文标签和说明
 * 你可以直接编辑此文件来调整各配置项的显示名称和描述
 */

export interface FieldLabel {
    label: string;
    description?: string;
}

/**
 * 配置分区标题翻译
 */
export const sectionLabels: Record<string, string> = {
    general: '通用',
    advanced: '高级',
    ehentai: 'E-Hentai',
    nhentai: 'NHentai',
    hdoujin: 'HDoujin',
    aria2: 'Aria2',
    komga: 'Komga',
    openai: 'OpenAI',
    comicinfo: 'ComicInfo'
};

/**
 * 获取分区标题
 */
export function getSectionLabel(section: string): string {
    return sectionLabels[section] ?? section;
}

export const configLabels: Record<string, Record<string, FieldLabel>> = {
    // ========== 通用配置 ==========
    general: {
        keep_torrents: {
            label: '保留种子文件',
            description: '下载完成后是否保留 torrent 文件'
        },
        keep_original_file: {
            label: '保留原始文件',
            description: '创建 .cbz 后是否保留原始文件'
        },
        prefer_japanese_title: {
            label: '优先使用日文标题',
            description: '当存在多语言标题时，优先使用日文标题'
        },
        move_path: {
            label: '完成后移动',
            description: '支持模板变量：{{author}}, {{series}}, {{title}}, {{filename}}, {{writer}}, {{penciller}}'
        }
    },

    // ========== 高级配置 ==========
    advanced: {
        tags_translation: {
            label: '标签翻译',
            description: '使用 EhTagTranslation 将标签翻译为中文'
        },
        remove_ads: {
            label: '移除广告页',
            description: '自动检测并移除广告页面'
        },
        aggressive_series_detection: {
            label: '激进的系列检测',
            description: '对 E-Hentai 的 AlternateSeries 字段进行更激进的检测'
        },
        openai_series_detection: {
            label: 'OpenAI 系列检测',
            description: '使用 OpenAI 接口对标题进行系列名和序号的智能识别'
        },
        prefer_openai_series: {
            label: '优先 OpenAI 系列识别',
            description: '优先使用 OpenAI 进行系列识别，正则作为后备方案'
        }
    },

    // ========== E-Hentai 配置 ==========
    ehentai: {
        ipb_member_id: {
            label: 'ipb_member_id',
            description: '从浏览器 Cookie 中获取的 ipb_member_id'
        },
        ipb_pass_hash: {
            label: 'ipb_pass_hash',
            description: '从浏览器 Cookie 中获取的 ipb_pass_hash'
        },
        favorite_sync: {
            label: '同步收藏夹',
            description: '定期同步 E-Hentai 收藏夹'
        },
        favorite_sync_interval: {
            label: '同步间隔',
            description: '收藏夹同步的时间间隔，如 6h、30m'
        },
        favcat_whitelist: {
            label: '收藏夹白名单',
            description: '仅同步指定的收藏夹分类（留空同步全部）'
        },
        initial_scan_pages: {
            label: '初始扫描页数',
            description: '首次同步时扫描的收藏夹页数'
        },
        auto_download_favorites: {
            label: '自动下载收藏',
            description: '检测到新增收藏时自动下载'
        },
        hath_check_enabled: {
            label: 'H@H 客户端检查',
            description: '检查 H@H 客户端在线状态'
        },
        hath_check_interval: {
            label: 'H@H 检查间隔',
            description: 'H@H 客户端状态检查的时间间隔'
        }
    },

    // ========== NHentai 配置 ==========
    nhentai: {
        cookie: {
            label: 'Cookie',
            description: '用于访问 NHentai 的浏览器 Cookie'
        }
    },

    // ========== HDoujin 配置 ==========
    hdoujin: {
        session_token: {
            label: '会话令牌',
            description: 'HDoujin 的 session token'
        },
        refresh_token: {
            label: '刷新令牌',
            description: '用于刷新会话的 refresh token'
        },
        clearance_token: {
            label: 'Cloudflare 令牌',
            description: 'Cloudflare clearance token'
        },
        user_agent: {
            label: 'User-Agent',
            description: '获取 clearance_token 时使用的浏览器 User-Agent'
        }
    },

    // ========== Aria2 配置 ==========
    aria2: {
        enable: {
            label: '启用 Aria2',
            description: '使用 Aria2 进行下载任务'
        },
        server: {
            label: '服务器地址',
            description: 'Aria2 RPC 服务器地址'
        },
        token: {
            label: 'RPC 密钥',
            description: 'Aria2 RPC 访问密钥'
        },
        download_dir: {
            label: '下载目录',
            description: 'Aria2 的下载保存目录'
        },
        mapped_dir: {
            label: '映射目录',
            description: '本地映射的下载目录路径（用于 Docker 环境）'
        }
    },

    // ========== Komga 配置 ==========
    komga: {
        enable: {
            label: '启用 Komga',
            description: '集成 Komga 漫画服务器'
        },
        server: {
            label: '服务器地址',
            description: 'Komga 服务器 URL'
        },
        username: {
            label: '用户名',
            description: 'Komga 登录用户名'
        },
        password: {
            label: '密码',
            description: 'Komga 登录密码'
        },
        library_id: {
            label: '库 ID',
            description: '要同步的 Komga 库 ID'
        },
        index_sync: {
            label: '索引同步',
            description: '定期同步 Komga 索引'
        },
        index_sync_interval: {
            label: '索引同步间隔',
            description: '索引同步的时间间隔'
        }
    },

    // ========== OpenAI 配置 ==========
    openai: {
        api_key: {
            label: 'API 密钥',
            description: 'OpenAI API 密钥'
        },
        base_url: {
            label: 'API 地址',
            description: '自定义 API 端点（留空使用官方地址）'
        },
        model: {
            label: '模型',
            description: '使用的 AI 模型名称'
        }
    },

    // ========== ComicInfo 配置 ==========
    comicinfo: {
        title: {
            label: '标题',
            description: 'Title - 系列标题'
        },
        writer: {
            label: '作者',
            description: 'Writer - 作者'
        },
        penciller: {
            label: '画师',
            description: 'Penciller - 画师'
        },
        translator: {
            label: '翻译者',
            description: 'Translator - 翻译者'
        },
        tags: {
            label: '标签',
            description: 'Tags - 标签'
        },
        web: {
            label: '来源链接',
            description: 'Web - 来源'
        },
        agerating: {
            label: '年龄分级',
            description: 'AgeRating - 年龄分级'
        },
        manga: {
            label: '漫画类型',
            description: 'Manga - 漫画阅读方向'
        },
        genre: {
            label: '类型',
            description: 'Genre - 流派'
        },
        languageiso: {
            label: '语言代码',
            description: 'LanguageISO - 语言'
        },
        number: {
            label: '序号',
            description: 'Number - 书籍序号'
        },
        alternateseries: {
            label: '系列名',
            description: 'AlternateSeries - 阅读列表标题，留空则不创建阅读列表'
        },
        alternatenumber: {
            label: '系列序号',
            description: 'AlternateNumber - 阅读列表中的序号'
        }
    }
};

/**
 * 获取字段标签，如果没有定义则返回原始 key
 */
export function getFieldLabel(section: string, key: string): string {
    return configLabels[section]?.[key]?.label ?? key;
}

/**
 * 获取字段描述
 */
export function getFieldDescription(section: string, key: string): string | undefined {
    return configLabels[section]?.[key]?.description;
}

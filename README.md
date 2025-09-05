# Hentai Assistant

一个全功能的EHentai下载助手，支持多种下载方式和自动化管理。

## 功能特性

- 🚀 **多下载方式**: 支持H@H Archive、Torrent下载
- 🎨 **元数据管理**: 自动生成ComicInfo.xml元数据
- 🌐 **标签翻译**: 支持EH标签中英文翻译
- 📚 **Komga集成**: 自动导入到Komga漫画库
- 📱 **Web界面**: 现代化的Vue.js管理界面
- 🔧 **配置管理**: 基于Web的配置界面
- 📊 **任务监控**: 实时下载进度和日志查看

## 快速开始

### 使用Docker运行

1. **Docker部署**

```bash
# 运行容器
docker run -d \
  -p 5001:5001 \
  -v $(pwd)/data:/app/data \
  --name hentai-assistant \
  ghcr.io/rosystain/hentai-assistant:latest
```

2. **访问Web界面**
   打开浏览器访问 `http://localhost:5001`

### 本地开发运行

1. **克隆项目**
   
   ```bash
   git clone https://github.com/<your-username>/hentai-assistant.git
   cd hentai-assistant
   ```

2. **安装Python依赖**
   
   ```bash
   pip install -r requirements.txt
   ```

3. **安装前端依赖**
   
   ```bash
   cd webui
   npm install
   ```

4. **启动开发服务器**
   
   ```bash
   # 终端1: 启动后端
   python src/main.py
   
   # 终端2: 启动前端开发服务器
   cd webui
   npm run dev
   ```

5. **访问开发环境**
   
   - 后端API: `http://localhost:5001`
   - 前端界面: `http://localhost:5173`

## 配置说明

### 配置文件格式

项目使用 INI 格式的配置文件。

### 配置文件结构

配置文件位于 `data/config.ini`，包含以下主要部分：

- **general**: 通用设置（下载选项、标签翻译等）
- **ehentai**: E-Hentai相关设置（Cookie、下载模式）
- **aria2**: Aria2 RPC设置（可选）
- **komga**: Komga API设置（可选）

### 必需配置

1. **E-Hentai Cookie**: 用于访问exhentai内容

### 可选配置

- **Aria2 RPC**: 启用Torrent下载功能
- **Komga API**: 启用自动导入到Komga
- **标签翻译**: 启用EH标签中英文翻译

### 配置示例

**INI格式示例:**

```ini
[general]
port=5001
download_torrent=false
tags_translation=true

[ehentai]
cookie="ipb_member_id=1234567; ipb_pass_hash=abcdef123456;"

[aria2]
enable=false
server=http://localhost:6800/jsonrpc
token=your_aria2_rpc_secret
```

## API接口

### 下载接口

```
GET /api/download?url=<gallery_url>&mode=<download_mode>
```

参数:

- `url`: E-Hentai画廊URL（必需）
- `mode`: 下载模式（可选，默认自动选择）

### 任务管理

- `GET /api/tasks`: 获取任务列表
- `GET /api/task_log/<task_id>`: 获取任务日志
- `POST /api/stop_task/<task_id>`: 停止任务
- `GET /api/task_stats`: 获取任务统计

### 配置管理

- `GET /api/config`: 获取当前配置
- `POST /api/config`: 更新配置


## 使用指南

### 1. 基本下载

通过Web界面或API发送下载请求：

```bash
curl "http://localhost:5001/api/download?url=https://exhentai.org/g/1234567/abcdefg/"
```

### 2. 批量下载

使用脚本批量处理：

```bash
#!/bin/bash
URLS=(
  "https://exhentai.org/g/1234567/abcdefg/"
  "https://exhentai.org/g/7654321/hijklmn/"
)

for url in "${URLS[@]}"; do
  curl "http://localhost:5001/api/download?url=$url"
  sleep 5
done
```

### 3. 集成Komga

配置Komga后，下载的文件会自动：

1. 添加元数据信息
2. 移动到Komga媒体库
3. 触发Komga扫描

## 故障排除

### 常见问题

1. **Cookie无效**
   
   - 检查E-Hentai Cookie是否过期
   - 确认可以正常访问exhentai

2. **下载失败**
   
   - 检查网络连接
   - 确认H@H权限

3. **Aria2连接失败**
   
   - 检查Aria2服务是否运行
   - 确认RPC密钥正确

### 日志查看

```bash
# 查看容器日志
docker logs hentai-assistant

# 查看应用日志
tail -f data/app.log
```

## 鸣谢

- 广告页检测: [hymbz/ComicReadScript](https://github.com/hymbz/ComicReadScript)
- 标签翻译数据库: [EhTagTranslation/Database](https://github.com/EhTagTranslation/Database)

## 支持

如有问题请提交Issue或联系维护者

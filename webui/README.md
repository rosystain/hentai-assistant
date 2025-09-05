# Web UI (Vue.js)

这是一个使用 Vue.js 构建的独立前端应用，用于管理 hentai-assistant 后端服务。

## 项目结构

前端应用位于 `webui/` 目录下。

## 开发设置

1. **进入前端项目目录:**
   
   ```bash
   cd webui
   ```

2. **安装依赖:**
   
   ```bash
   npm install
   ```

3. **运行开发服务器:**
   
   ```bash
   npm run dev
   ```
   
   这将在 `http://localhost:5173` 启动一个开发服务器。

## 构建生产版本

1. **进入前端项目目录:**
   
   ```bash
   cd webui
   ```

2. **构建应用:**
   
   ```bash
   npm run build
   ```
   
   这将在 `webui/dist/` 目录下生成生产就绪的静态文件。

## 与 Flask 后端集成和部署

### 开发环境

在开发环境中，Vue.js 开发服务器 (通常在 `http://localhost:5173`) 会通过代理 (`vite.config.ts` 中配置) 将 `/api` 请求转发到 Flask 后端 (通常在 `http://127.0.0.1:5001`)。

1. **启动 Flask 后端:**
   
   ```bash
   python src/main.py
   ```

2. **启动 Vue.js 开发服务器:**
   
   ```bash
   cd webui
   npm run dev
   ```
   
   然后通过 `http://localhost:5173` 访问前端应用。

### 生产环境

在生产环境中，Flask 后端将负责提供 Vue.js 构建后的静态文件。

1. **构建 Vue.js 应用:**
   
   ```bash
   cd webui
   npm run build
   ```
   
   这将生成 `webui/dist/` 目录。

2. **启动 Flask 后端:**
   
   ```bash
   python src/main.py
   ```
   
   Flask 应用现在将从 `webui/dist` 目录提供静态文件，并通过根路由 (`/`) 服务 `index.html`。
   您可以通过 `http://127.0.0.1:5001` (或您在 `config.ini` 中配置的端口) 访问整个应用。

## 注意事项

* 确保您的 Node.js 版本符合 Vue.js 项目的要求。
* Flask 后端已配置 CORS，允许跨域请求。
* Flask 后端在调试模式下会将前端请求重定向到 Vue 开发服务器，在生产模式下则直接提供静态文件。

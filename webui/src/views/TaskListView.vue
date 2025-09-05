<template>
  <div class="task-list-view">
    <!-- 通知系统 -->
    <div class="notifications-container">
      <div
        v-for="notification in notifications"
        :key="notification.id"
        :class="['notification', `notification-${notification.type}`]"
        @click="removeNotification(notification.id)"
      >
        <div class="notification-content">
          <span class="notification-icon">
            {{ notification.type === 'success' ? '✅' :
                notification.type === 'error' ? '❌' :
                notification.type === 'warning' ? '⚠️' : 'ℹ️' }}
          </span>
          <span class="notification-message">{{ notification.message }}</span>
        </div>
        <button class="notification-close" @click.stop="removeNotification(notification.id)">
          ✕
        </button>
      </div>
    </div>

    <h1>下载任务列表</h1>

    <!-- 搜索框 -->
    <div class="search-section">
      <div class="search-input-container">
        <input
          type="text"
          v-model="searchQuery"
          placeholder="搜索任务ID、文件名..."
          class="search-input"
          @input="handleSearch"
        />
        <button
          v-if="searchQuery"
          @click="clearSearch"
          class="clear-search-button"
          title="清除搜索"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- 状态过滤器 -->
    <div class="filter-controls">
      <div class="status-filters">
        <button
          v-for="filter in statusFilters"
          :key="filter.key"
          @click="setStatusFilter(filter.key)"
          :class="['filter-button', { active: currentFilter === filter.key }]"
        >
          {{ filter.label }}
          <span class="task-count">({{ getTaskCount(filter.key) }})</span>
        </button>
      </div>

      <!-- 清除记录按钮 -->
      <div class="action-controls">
        <div class="clear-controls" v-if="currentFilter !== 'in-progress'">
          <button
            @click="confirmClearTasks"
            :disabled="paginatedTasks.length === 0 || clearing"
            class="clear-button"
          >
            {{ clearing ? '清除中...' : '清除记录' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="loading" class="loading-message">加载中...</div>
    <div v-else-if="error" class="error-message">{{ error }}</div>
    <div v-else>
      <div v-if="paginatedTasks.length === 0" class="info-message">
        {{ getEmptyMessage() }}
      </div>
      <div v-else>
        <!-- 任务统计信息 -->
        <div class="task-stats">
          <span>共 {{ pagination.total }} 个任务</span>
          <span v-if="pagination.total_pages > 1">
            (第 {{ pagination.page }} / {{ pagination.total_pages }} 页)
          </span>
        </div>

        <div class="task-cards" :key="taskListKey">
          <div v-for="task in paginatedTasks" :key="task.id" class="task-card">
            <div class="task-header">
              <h3 :title="task.filename || '未知文件名'">{{ formatFilename(task.filename) || '未知文件名' }}</h3>
              <span :class="statusClass(task.status)">{{ statusText(task.status) }}</span>
            </div>
            <p class="task-id-subtitle">任务ID: {{ task.id }}</p>
            <div v-if="task.error" class="task-error">
              <strong>错误:</strong> {{ task.error }}
            </div>

            <!-- 进度条显示 -->
            <div v-if="task.status === '进行中'" class="progress-container">
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: task.progress + '%' }"
                  :title="`${task.progress}% - ${formatBytes(task.downloaded)}/${formatBytes(task.total_size)}`"
                ></div>
              </div>
              <div class="progress-info">
                <span class="progress-percentage">{{ task.progress }}%</span>
                <span class="progress-details">
                  {{ formatBytes(task.downloaded) }}/{{ formatBytes(task.total_size) }}
                  ({{ formatSpeed(task.speed) }})
                </span>
              </div>
            </div>

            <div class="task-actions">
              <button
                v-if="task.url"
                @click="openGallery(task.url)"
                class="gallery-button"
              >
                跳转画廊
              </button>
              <button @click="toggleLog(task.id)" class="log-button">
                {{ expandedLogs[task.id] ? '隐藏日志' : '查看日志' }}
              </button>
              <button
                v-if="task.status === '错误'"
                @click="retryTask(task.id)"
                :disabled="retryingTasks[task.id]"
                class="retry-button"
              >
                {{ retryingTasks[task.id] ? '重试中...' : '重试' }}
              </button>
              <button
                v-if="task.status === '进行中'"
                @click="stopTask(task.id)"
                :disabled="stoppingTasks[task.id]"
                class="stop-button"
              >
                {{ stoppingTasks[task.id] ? '停止中...' : '停止任务' }}
              </button>
            </div>
            <div v-if="expandedLogs[task.id]" class="task-log-container">
              <div class="task-log-header">
                <h4>任务日志:</h4>
                <div class="log-actions">
                  <button @click="copyLog(task.log)" class="copy-log-button" title="复制日志">
                    📋 复制
                  </button>
                  <button @click="toggleLog(task.id)" class="close-log-button" title="关闭日志">
                    ✕
                  </button>
                </div>
              </div>
              <div class="task-log-content">
                <pre class="log-text">{{ task.log || '无日志信息。' }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 分页控件 -->
        <div v-if="pagination.total_pages > 1" class="pagination">
          <button
            @click="changePage(pagination.page - 1)"
            :disabled="pagination.page <= 1"
            class="page-button"
          >
            上一页
          </button>

          <div class="page-numbers">
            <template v-for="(pageItem, index) in getVisiblePages()" :key="index">
              <button
                v-if="typeof pageItem === 'number'"
                @click="changePage(pageItem)"
                :class="['page-number', { active: pageItem === pagination.page }]"
              >
                {{ pageItem }}
              </button>
              <span v-else class="page-ellipsis">...</span>
            </template>
          </div>

          <button
            @click="changePage(pagination.page + 1)"
            :disabled="pagination.page >= pagination.total_pages"
            class="page-button"
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue';
import axios from 'axios';
import { useTheme } from '@/composables/useTheme';

// 通知系统
interface Notification {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  duration?: number;
}

const notifications = ref<Notification[]>([]);

interface Task {
  id: string;
  status: string;
  error: string | null;
  log: string | null;
  filename: string | null; // 添加 filename 属性
  progress: number; // 进度百分比
  downloaded: number; // 已下载字节数
  total_size: number; // 总字节数
  speed: number; // 下载速度 B/s
  url?: string; // 画廊URL
}

const tasks = ref<Task[]>([]);
const loading = ref(true);
const refreshing = ref(false); // 新增：自动刷新状态
const error = ref<string | null>(null);
const expandedLogs = ref<{ [key: string]: boolean }>({});
const stoppingTasks = ref<{ [key: string]: boolean }>({});
const retryingTasks = ref<{ [key: string]: boolean }>({});
const currentFilter = ref<string>('all'); // 当前选中的过滤器
const clearing = ref(false); // 清除任务状态
const searchQuery = ref<string>(''); // 搜索查询
let refreshInterval: number | undefined;
let refreshTimeout: number | undefined;
const { isDark } = useTheme();

// 分页相关状态
const pagination = ref({
  page: 1,
  page_size: 10,
  total: 0,
  total_pages: 0,
  status_counts: {
    all: 0,
    'in-progress': 0,
    completed: 0,
    cancelled: 0,
    failed: 0
  }
} as {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  status_counts?: {
    all: number;
    'in-progress': number;
    completed: number;
    cancelled: number;
    failed: number;
  };
});

const API_BASE_URL = '/api'; // 使用相对路径，通过 Vite 代理或 Flask 静态服务处理

// 状态过滤器定义
const statusFilters = [
  { key: 'all', label: '全部任务' },
  { key: 'in-progress', label: '进行中' },
  { key: 'completed', label: '已完成' },
  { key: 'cancelled', label: '取消' },
  { key: 'failed', label: '失败' }
];

// 分页后的任务列表（从后端获取并应用搜索过滤）
const paginatedTasks = computed(() => {
  let filteredTasks = tasks.value;

  // 应用搜索过滤
  if (searchQuery.value.trim()) {
    const query = searchQuery.value.toLowerCase().trim();
    filteredTasks = filteredTasks.filter(task => {
      // 搜索任务ID
      if (task.id.toLowerCase().includes(query)) {
        return true;
      }
      // 搜索文件名
      if (task.filename && task.filename.toLowerCase().includes(query)) {
        return true;
      }
      // 搜索URL
      if (task.url && task.url.toLowerCase().includes(query)) {
        return true;
      }
      // 搜索状态文本
      if (statusText(task.status).toLowerCase().includes(query)) {
        return true;
      }
      return false;
    });
  }

  return filteredTasks;
});

// 优化任务列表更新，避免不必要的重新渲染
const taskListKey = computed(() => {
  return tasks.value.map(task => `${task.id}-${task.status}-${task.progress}`).join('|');
});


const fetchTasks = async (isInitialLoad = false) => {
  if (isInitialLoad) {
    loading.value = true;
  } else {
    refreshing.value = true;
  }
  error.value = null;
  try {
    const params = new URLSearchParams({
      page: pagination.value.page.toString(),
      page_size: pagination.value.page_size.toString()
    });

    if (currentFilter.value !== 'all') {
      params.append('status', currentFilter.value);
    }

    const response = await axios.get(`${API_BASE_URL}/tasks?${params}`);
    const data = response.data;

    tasks.value = data.tasks || [];
    pagination.value = {
      page: data.page || 1,
      page_size: data.page_size || 20,
      total: data.total || 0,
      total_pages: data.total_pages || 0,
      status_counts: data.status_counts || {
        all: 0,
        'in-progress': 0,
        completed: 0,
        cancelled: 0,
        failed: 0
      }
    };
  } catch (err) {
    error.value = '无法加载任务列表。请检查后端服务是否运行。';
    console.error(err);
  } finally {
    if (isInitialLoad) {
      loading.value = false;
    } else {
      refreshing.value = false;
    }
  }
};

const toggleLog = (taskId: string) => {
  expandedLogs.value[taskId] = !expandedLogs.value[taskId];
};

// 通知系统函数
const showNotification = (message: string, type: 'success' | 'error' | 'warning' | 'info' = 'info', duration = 3000) => {
  const id = Date.now().toString();
  const notification: Notification = { id, type, message, duration };
  notifications.value.push(notification);

  if (duration > 0) {
    setTimeout(() => {
      removeNotification(id);
    }, duration);
  }
};

const removeNotification = (id: string) => {
  const index = notifications.value.findIndex(n => n.id === id);
  if (index > -1) {
    notifications.value.splice(index, 1);
  }
};

// 确认对话框系统
const showConfirmDialog = (message: string): Promise<boolean> => {
  return new Promise((resolve) => {
    // 检查是否处于深色模式
    const isDark = document.documentElement.classList.contains('dark');

    const modal = document.createElement('div');
    modal.className = 'confirm-dialog-modal';
    modal.style.cssText = `
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: ${isDark ? 'rgba(0, 0, 0, 0.7)' : 'rgba(0, 0, 0, 0.5)'};
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 10001;
    `;

    const dialog = document.createElement('div');
    dialog.className = 'confirm-dialog';
    dialog.style.cssText = `
      background: ${isDark ? 'rgba(33, 37, 41, 0.95)' : 'white'};
      border: ${isDark ? '1px solid rgba(255, 255, 255, 0.2)' : 'none'};
      color: ${isDark ? '#ffffff' : '#333'};
      border-radius: 8px;
      padding: 24px;
      max-width: 400px;
      width: 90%;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    `;

    // 创建标题
    const title = document.createElement('h3');
    title.textContent = '确认操作';
    title.style.cssText = `margin: 0 0 16px 0; color: ${isDark ? '#ffffff' : '#333'};`;

    // 创建消息文本
    const messageEl = document.createElement('p');
    messageEl.textContent = message;
    messageEl.style.cssText = `margin: 0 0 24px 0; color: ${isDark ? '#ffffff' : '#666'};`;

    // 创建按钮容器
    const buttonContainer = document.createElement('div');
    buttonContainer.style.cssText = 'display: flex; gap: 12px; justify-content: flex-end;';

    // 创建取消按钮
    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = '取消';
    cancelBtn.id = 'cancel-btn';
    cancelBtn.style.cssText = `
      padding: 8px 16px;
      background: ${isDark ? 'rgba(255, 255, 255, 0.1)' : '#6c757d'};
      color: ${isDark ? '#ffffff' : 'white'};
      border: ${isDark ? '1px solid rgba(255, 255, 255, 0.2)' : 'none'};
      border-radius: 4px;
      cursor: pointer;
    `;

    // 创建确认按钮
    const confirmBtn = document.createElement('button');
    confirmBtn.textContent = '确认';
    confirmBtn.id = 'confirm-btn';
    confirmBtn.style.cssText = `
      padding: 8px 16px;
      background: ${isDark ? 'rgba(220, 53, 69, 0.8)' : '#dc3545'};
      color: white;
      border: ${isDark ? '1px solid rgba(220, 53, 69, 0.8)' : 'none'};
      border-radius: 4px;
      cursor: pointer;
    `;

    buttonContainer.appendChild(cancelBtn);
    buttonContainer.appendChild(confirmBtn);
    dialog.appendChild(title);
    dialog.appendChild(messageEl);
    dialog.appendChild(buttonContainer);


    const cleanup = () => {
      if (document.body.contains(modal)) {
        document.body.removeChild(modal);
      }
    };

    cancelBtn?.addEventListener('click', () => {
      cleanup();
      resolve(false);
    });

    confirmBtn?.addEventListener('click', () => {
      cleanup();
      resolve(true);
    });

    modal.onclick = (e) => {
      if (e.target === modal) {
        cleanup();
        resolve(false);
      }
    };

    modal.appendChild(dialog);
    document.body.appendChild(modal);
  });
};

const copyLog = async (logContent: string | null) => {
  if (!logContent) {
    showNotification('没有日志内容可复制', 'warning');
    return;
  }

  try {
    // 检查是否支持 Clipboard API
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(logContent);
      showNotification('日志已复制到剪贴板', 'success');
      return;
    }

    // 如果不支持 Clipboard API，直接显示文本供用户手动复制
    throw new Error('Clipboard API not supported');
  } catch (err) {
    // 显示模态框供用户手动复制
    console.warn('自动复制失败，显示手动复制界面:', err);
    showCopyModal(logContent);
  }
};

// 显示复制模态框的辅助函数
const showCopyModal = (content: string) => {
  const modal = document.createElement('div');
  modal.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 10000;
  `;

  const dialog = document.createElement('div');
  dialog.style.cssText = `
    background: white;
    border-radius: 8px;
    padding: 24px;
    max-width: 600px;
    max-height: 80vh;
    width: 90%;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    display: flex;
    flex-direction: column;
  `;

  const header = document.createElement('div');

  // 创建标题
  const title = document.createElement('h3');
  title.textContent = '📋 复制日志内容';
  title.style.cssText = 'margin: 0 0 16px 0; color: #333; font-size: 18px;';

  // 创建说明文本
  const description = document.createElement('p');
  description.textContent = '请选择下方文本内容并手动复制 (Ctrl+C / Cmd+C)';
  description.style.cssText = 'margin: 0 0 16px 0; color: #666; font-size: 14px;';

  header.appendChild(title);
  header.appendChild(description);

  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.style.cssText = `
    width: 100%;
    height: 300px;
    border: 2px solid #007bff;
    border-radius: 6px;
    padding: 12px;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
    font-size: 13px;
    line-height: 1.4;
    resize: vertical;
    background: #f8f9fa;
    margin-bottom: 16px;
  `;
  textarea.readOnly = true;

  const buttonContainer = document.createElement('div');
  buttonContainer.style.cssText = `
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  `;

  const selectAllBtn = document.createElement('button');
  selectAllBtn.textContent = '全选';
  selectAllBtn.style.cssText = `
    padding: 8px 16px;
    background: #6c757d;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
  `;
  selectAllBtn.onclick = () => {
    textarea.select();
    textarea.setSelectionRange(0, 99999); // 确保在移动设备上也能选中
  };

  const closeBtn = document.createElement('button');
  closeBtn.textContent = '关闭';
  closeBtn.style.cssText = `
    padding: 8px 16px;
    background: #007bff;
    color: white;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
  `;
  closeBtn.onclick = () => document.body.removeChild(modal);

  // 点击背景关闭
  modal.onclick = (e) => {
    if (e.target === modal) {
      document.body.removeChild(modal);
    }
  };

  // ESC 键关闭
  const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      document.body.removeChild(modal);
      document.removeEventListener('keydown', handleKeydown);
    }
  };
  document.addEventListener('keydown', handleKeydown);

  buttonContainer.appendChild(selectAllBtn);
  buttonContainer.appendChild(closeBtn);
  dialog.appendChild(header);
  dialog.appendChild(textarea);
  dialog.appendChild(buttonContainer);
  modal.appendChild(dialog);
  document.body.appendChild(modal);

  // 自动选择文本并聚焦
  setTimeout(() => {
    textarea.focus();
    textarea.select();
  }, 100);
};

const stopTask = async (taskId: string) => {
  stoppingTasks.value[taskId] = true;
  try {
    await axios.post(`${API_BASE_URL}/stop_task/${taskId}`);
    // 任务停止后，刷新列表
    await fetchTasks(false);
  } catch (err: any) {
    console.error(`停止任务 ${taskId} 失败:`, err);
    showNotification(`停止任务失败: ${err.response?.data?.message || err.message}`, 'error');
  } finally {
    stoppingTasks.value[taskId] = false;
  }
};

const retryTask = async (taskId: string) => {
  retryingTasks.value[taskId] = true;

  try {
    // 发送重试请求到后端
    const response = await axios.post(`${API_BASE_URL}/retry_task/${taskId}`);

    showNotification('任务重试已启动', 'success');

    // 延迟刷新列表，确保获取到新的重试任务
    setTimeout(async () => {
      await fetchTasks(false);
    }, 1000);

  } catch (err: any) {
    console.error(`重试任务 ${taskId} 失败:`, err);
    showNotification(`重试任务失败: ${err.response?.data?.message || err.message}`, 'error');
    // 如果重试失败，刷新列表以恢复状态
    await fetchTasks(false);
  } finally {
    retryingTasks.value[taskId] = false;
  }
};

const openGallery = (url: string) => {
  if (url) {
    window.open(url, '_blank');
  }
};


const statusClass = (status: string) => {
  if (status === '完成') return 'status-success';
  if (status === '取消') return 'status-cancelled';
  if (status === '错误') return 'status-error';
  return 'status-in-progress';
};

const statusText = (status: string) => {
  if (status === '完成') return '✅ 完成';
  if (status === '取消') return '❌ 取消';
  if (status === '错误') return '⚠️ 错误';
  return '⏳ 进行中';
};

// 格式化文件名显示
const formatFilename = (filename: string | null): string => {
  if (!filename) return '';

  // 处理特殊字符和过长文件名
  let formatted = filename;

  // 移除常见的文件扩展名
  formatted = formatted.replace(/\.(zip|cbz|torrent)$/i, '');

  // 解码HTML实体编码（如 &#039; 转换为 '）
  formatted = formatted
    .replace(/&#039;/g, "'")    // 单引号
    .replace(/"/g, '"')   // 双引号
    .replace(/&/g, '&')    // &符号
    .replace(/</g, '<')     // 小于号
    .replace(/>/g, '>')     // 大于号
    .replace(/&nbsp;/g, ' ');  // 空格

  // 解码URL编码的字符（如果有）
  try {
    formatted = decodeURIComponent(formatted);
  } catch (e) {
    // 如果解码失败，保持原样
  }

  // 替换常见的特殊字符
  formatted = formatted
    .replace(/%20/g, ' ')   // 替换URL空格
    .replace(/_/g, ' ')     // 替换下划线为空格
    .trim();

  // 如果文件名过长，截断并添加省略号
  const maxLength = 50;
  if (formatted.length > maxLength) {
    formatted = formatted.substring(0, maxLength - 3) + '...';
  }

  return formatted;
};

// 格式化字节大小为易读格式
const formatBytes = (bytes: number): string => {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// 格式化下载速度
const formatSpeed = (bytesPerSecond: number): string => {
  if (bytesPerSecond === 0) return '0 B/s';
  const k = 1024;
  const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
  const i = Math.floor(Math.log(bytesPerSecond) / Math.log(k));
  return parseFloat((bytesPerSecond / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
};

// 设置状态过滤器
const setStatusFilter = (filter: string) => {
  currentFilter.value = filter;
  pagination.value.page = 1; // 重置到第一页
  fetchTasks(false); // 重新获取任务
};

// 处理搜索输入
const handleSearch = () => {
  // 搜索时重置到第一页
  pagination.value.page = 1;
  // 由于搜索是客户端过滤，不需要重新获取数据
};

// 清除搜索
const clearSearch = () => {
  searchQuery.value = '';
  pagination.value.page = 1;
};

// 分页相关方法
const changePage = (page: number) => {
  if (page >= 1 && page <= pagination.value.total_pages) {
    pagination.value.page = page;
    fetchTasks(false);
  }
};

// 获取可见的页码
const getVisiblePages = (): (number | { type: 'ellipsis' })[] => {
  const current = pagination.value.page;
  const total = pagination.value.total_pages;
  const visible: (number | { type: 'ellipsis' })[] = [];

  if (total <= 7) {
    // 总页数较少时显示所有页码
    for (let i = 1; i <= total; i++) {
      visible.push(i);
    }
  } else {
    // 总页数较多时显示部分页码
    if (current <= 4) {
      for (let i = 1; i <= 5; i++) {
        visible.push(i);
      }
      visible.push({ type: 'ellipsis' }); // 省略号
      visible.push(total);
    } else if (current >= total - 3) {
      visible.push(1);
      visible.push({ type: 'ellipsis' }); // 省略号
      for (let i = total - 4; i <= total; i++) {
        visible.push(i);
      }
    } else {
      visible.push(1);
      visible.push({ type: 'ellipsis' }); // 省略号
      for (let i = current - 1; i <= current + 1; i++) {
        visible.push(i);
      }
      visible.push({ type: 'ellipsis' }); // 省略号
      visible.push(total);
    }
  }

  return visible;
};

// 获取任务数量（从后端返回的统计信息中获取）
const getTaskCount = (filter: string): number => {
  // 使用后端返回的准确统计信息
  const statusCounts = pagination.value.status_counts;
  if (statusCounts && statusCounts[filter as keyof typeof statusCounts] !== undefined) {
    return statusCounts[filter as keyof typeof statusCounts];
  }

  // 降级方案：使用当前页面数据（仅用于兼容性）
  if (filter === 'all') {
    return pagination.value.total;
  }

  return tasks.value.filter(task => {
    switch (filter) {
      case 'in-progress':
        return task.status === '进行中';
      case 'completed':
        return task.status === '完成';
      case 'cancelled':
        return task.status === '取消';
      case 'failed':
        return task.status === '错误';
      default:
        return false;
    }
  }).length;
};


// 获取空列表时的提示消息
const getEmptyMessage = (): string => {
  switch (currentFilter.value) {
    case 'in-progress':
      return '暂无进行中的下载任务。';
    case 'completed':
      return '暂无已完成的下载任务。';
    case 'cancelled':
      return '暂无取消的下载任务。';
    case 'failed':
      return '暂无失败的下载任务。';
    default:
      return '暂无下载任务。';
  }
};

// 确认清除任务
const confirmClearTasks = async () => {
  let statusToClear: string;
  let statusName: string;

  if (currentFilter.value === 'completed') {
    statusToClear = '完成';
    statusName = '已完成';
  } else if (currentFilter.value === 'cancelled') {
    statusToClear = '取消';
    statusName = '取消';
  } else if (currentFilter.value === 'failed') {
    statusToClear = '失败';
    statusName = '失败';
  } else if (currentFilter.value === 'all') {
    statusToClear = 'all_except_in_progress';
    statusName = '全部（除进行中任务外）';
  } else {
    return;
  }

  const confirmed = await showConfirmDialog(`确定要清除所有${statusName}的任务记录吗？此操作不可撤销。`);
  if (confirmed) {
    clearTasks(statusToClear);
  }
};

// 清除特定状态的任务
const clearTasks = async (status: string) => {
  clearing.value = true;
  try {
    await axios.post(`${API_BASE_URL}/clear_tasks?status=${status}`);
    // 清除成功后重置到第一页并刷新任务列表
    pagination.value.page = 1;
    await fetchTasks(false);
  } catch (err: any) {
    console.error(`清除任务失败:`, err);
    showNotification(`清除任务失败: ${err.response?.data?.message || err.message}`, 'error');
  } finally {
    clearing.value = false;
  }
};

// 智能刷新管理
const startSmartRefresh = () => {
  const hasActiveTasks = tasks.value.some(task => task.status === '进行中');
  const interval = hasActiveTasks ? 3000 : 10000; // 有活动任务时3秒刷新，无活动任务时10秒刷新

  if (refreshTimeout) {
    clearTimeout(refreshTimeout);
  }

  refreshTimeout = setTimeout(async () => {
    await fetchTasks(false);
    startSmartRefresh(); // 递归调用以适应任务状态变化
  }, interval);
};

onMounted(() => {
  fetchTasks(true); // 初始加载
  startSmartRefresh(); // 开始智能刷新
});

onUnmounted(() => {
  if (refreshTimeout) {
    clearTimeout(refreshTimeout);
  }
});
</script>

<style scoped>
.task-list-view {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  text-align: center;
  margin-bottom: 30px;
}

.task-cards {
  display: grid;
  gap: 20px;
  transition: opacity 0.3s ease;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
}

.task-card {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  transform: translateY(0);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
  position: relative;
}

.task-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: linear-gradient(90deg, #007bff 0%, #28a745 50%, #6f42c1 100%);
  border-radius: 12px 12px 0 0;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.task-card:hover::before {
  opacity: 1;
}

.task-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15), 0 4px 10px rgba(0, 0, 0, 0.1);
  border-color: #dee2e6;
}

.task-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  gap: 15px; /* 添加间距防止挤压 */
}

.task-header h3 {
  margin: 0;
  color: #333;
  font-size: 1.2em; /* 稍微增大主标题字体 */
  flex: 1; /* 允许标题占据剩余空间 */
  min-width: 0; /* 防止标题溢出 */
  overflow-wrap: break-word;
  word-wrap: break-word;
  hyphens: auto;
  line-height: 1.3;
}

.status-success,
.status-cancelled,
.status-error,
.status-in-progress {
  font-weight: bold;
  white-space: nowrap; /* 防止状态文本换行 */
  flex-shrink: 0; /* 防止状态文本被压缩 */
}

.task-id-subtitle {
  font-size: 0.9em;
  color: #666;
  margin-top: 5px;
  margin-bottom: 10px;
}

.status-success {
  color: #28a745; /* Green */
}

.status-cancelled {
  color: #6c757d; /* Gray */
}

.status-error {
  color: #dc3545; /* Red */
}

.status-in-progress {
  color: #ffc107; /* Yellow/Orange */
}

.task-error {
  color: #dc3545;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  padding: 8px;
  border-radius: 4px;
  margin-top: 10px;
  font-size: 0.9em;
}

.task-actions {
  margin-top: 15px;
  display: flex;
  gap: 10px;
}

.log-button, .stop-button, .retry-button, .gallery-button, .refresh-button {
  padding: 8px 15px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

.log-button {
  background-color: #007bff;
  color: white;
}

.log-button:hover {
  background-color: #0056b3;
}

.gallery-button {
  background-color: #6f42c1;
  color: white;
}

.gallery-button:hover {
  background-color: #5a359a;
}

.retry-button {
  background-color: #28a745;
  color: white;
}

.retry-button:hover {
  background-color: #1e7e34;
}

.retry-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.stop-button {
  background-color: #dc3545;
  color: white;
}

.stop-button:hover {
  background-color: #c82333;
}

.stop-button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}

.task-log-container {
  background-color: #f8f9fa;
  border: 1px solid #dee2e6;
  border-radius: 8px;
  margin-top: 15px;
  overflow: hidden;
  animation: slideDown 0.3s ease-out;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.task-log-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  background-color: #e9ecef;
  border-bottom: 1px solid #dee2e6;
}

.task-log-header h4 {
  margin: 0;
  color: #495057;
  font-size: 1em;
  font-weight: 600;
}

.log-actions {
  display: flex;
  gap: 8px;
}

.copy-log-button, .close-log-button {
  padding: 6px 10px;
  border: 1px solid #dee2e6;
  border-radius: 4px;
  background-color: white;
  color: #495057;
  cursor: pointer;
  font-size: 0.8em;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.copy-log-button:hover {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

.close-log-button:hover {
  background-color: #dc3545;
  color: white;
  border-color: #dc3545;
}

.task-log-content {
  max-height: 400px;
  overflow-y: auto;
  padding: 0;
}

.log-text {
  margin: 0;
  padding: 15px;
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Courier New', monospace;
  font-size: 0.9em;
  line-height: 1.5;
  color: #212529;
  white-space: pre-wrap;
  word-break: break-word;
  background-color: #ffffff;
  border: none;
  min-height: 100px;
}

/* 自定义滚动条样式 */
.task-log-content::-webkit-scrollbar {
  width: 8px;
}

.task-log-content::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

.task-log-content::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 4px;
}

.task-log-content::-webkit-scrollbar-thumb:hover {
  background: #a8a8a8;
}

/* 展开动画 */
@keyframes slideDown {
  from {
    opacity: 0;
    max-height: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    max-height: 500px;
    transform: translateY(0);
  }
}


.search-section {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
}

.search-input-container {
  position: relative;
  display: flex;
  align-items: center;
  max-width: 400px;
  width: 100%;
}

.filter-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 15px;
  background-color: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e9ecef;
}

.status-filters {
  display: flex;
  gap: 10px;
}

.filter-button {
  padding: 8px 16px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  background-color: white;
  color: #495057;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9em;
}

.filter-button:hover {
  background-color: #e9ecef;
  border-color: #adb5bd;
}

.filter-button.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

.task-count {
  font-size: 0.8em;
  opacity: 0.8;
  margin-left: 4px;
}

.search-input-container {
  position: relative;
  display: flex;
  align-items: center;
  max-width: 400px;
  width: 100%;
}

.search-input {
  width: 100%;
  padding: 8px 35px 8px 12px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  font-size: 0.9em;
  background-color: white;
  color: #495057;
  transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.search-input:focus {
  border-color: #007bff;
  outline: none;
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25);
}

.clear-search-button {
  position: absolute;
  right: 8px;
  top: 50%;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: #6c757d;
  cursor: pointer;
  font-size: 14px;
  padding: 2px;
  border-radius: 50%;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.clear-search-button:hover {
  background-color: #f8f9fa;
  color: #495057;
}

.action-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.clear-controls {
  display: flex;
  align-items: center;
}

.clear-button {
  padding: 8px 16px;
  border: none;
  border-radius: 5px;
  background-color: #dc3545;
  color: white;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9em;
}

.clear-button:hover:not(:disabled) {
  background-color: #c82333;
}

.clear-button:disabled {
  background-color: #6c757d;
  border-color: #6c757d;
  cursor: not-allowed;
  opacity: 0.6;
}

.info-message, .error-message, .loading-message {
  padding: 10px;
  border-radius: 5px;
  margin-top: 20px;
  text-align: center;
}

.info-message {
  background-color: #e2e6ea;
  color: #383d41;
  border: 1px solid #d6d8db;
}

.loading-message {
  background-color: #d1ecf1;
  color: #0c5460;
  border: 1px solid #bee5eb;
}

.error-message {
  background-color: #f8d7da;
  color: #dc3545;
  border: 1px solid #f5c6cb;
}

/* 进度条样式 */
.progress-container {
  margin-top: 15px;
  margin-bottom: 15px;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background-color: #e9ecef;
  border-radius: 4px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background-color: #007bff;
  border-radius: 4px;
  transition: width 0.5s ease-out;
  transform-origin: left;
}

.progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
  font-size: 0.85em;
  color: #6c757d;
}

.progress-percentage {
  font-weight: bold;
  color: #007bff;
}

.progress-details {
  font-size: 0.8em;
}

/* 任务统计样式 */
.task-stats {
  margin-bottom: 15px;
  padding: 10px;
  background-color: #f8f9fa;
  border-radius: 5px;
  color: #6c757d;
  text-align: center;
  font-size: 0.9em;
  transition: all 0.3s ease;
}

/* 分页样式 */
.pagination {
  display: flex;
  justify-content: center;
  align-items: center;
  margin-top: 30px;
  gap: 10px;
}

.page-button {
  padding: 8px 16px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  background-color: white;
  color: #495057;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9em;
}

.page-button:hover:not(:disabled) {
  background-color: #e9ecef;
  border-color: #adb5bd;
}

.page-button:disabled {
  background-color: #f8f9fa;
  color: #6c757d;
  cursor: not-allowed;
  opacity: 0.6;
}

.page-numbers {
  display: flex;
  gap: 5px;
}

.page-number {
  padding: 8px 12px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  background-color: white;
  color: #495057;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 0.9em;
  min-width: 40px;
  text-align: center;
}

.page-number:hover {
  background-color: #e9ecef;
  border-color: #adb5bd;
}

.page-number.active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}

.page-number:disabled {
  background-color: #f8f9fa;
  color: #6c757d;
  cursor: default;
  border: none;
}

.page-ellipsis {
  padding: 8px 12px;
  color: #6c757d;
  font-size: 0.9em;
  user-select: none;
}
/* 通知系统样式 */
.notifications-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 400px;
}

.notification {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  transition: all 0.3s ease;
  animation: slideInRight 0.3s ease-out;
  min-height: 60px;
}

.notification:hover {
  transform: translateX(-4px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.notification-success {
  background: #d4edda;
  border: 1px solid #c3e6cb;
  color: #155724;
}

.notification-error {
  background: #f8d7da;
  border: 1px solid #f5c6cb;
  color: #721c24;
}

.notification-warning {
  background: #fff3cd;
  border: 1px solid #ffeaa7;
  color: #856404;
}

.notification-info {
  background: #d1ecf1;
  border: 1px solid #bee5eb;
  color: #0c5460;
}

.notification-content {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.notification-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.notification-message {
  font-size: 14px;
  line-height: 1.4;
  word-break: break-word;
}

.notification-close {
  background: none;
  border: none;
  font-size: 16px;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  color: inherit;
  opacity: 0.7;
  transition: opacity 0.2s ease;
  flex-shrink: 0;
  margin-left: 8px;
}

.notification-close:hover {
  opacity: 1;
  background: rgba(0, 0, 0, 0.1);
}

@keyframes slideInRight {
  from {
    opacity: 0;
    transform: translateX(100%);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

/* 深色模式下的通知样式 */
.dark .notification-success {
  background: rgba(40, 167, 69, 0.2);
  border-color: rgba(40, 167, 69, 0.3);
  color: #28a745;
}

.dark .notification-error {
  background: rgba(220, 53, 69, 0.2);
  border-color: rgba(220, 53, 69, 0.3);
  color: #dc3545;
}

.dark .notification-warning {
  background: rgba(255, 193, 7, 0.2);
  border-color: rgba(255, 193, 7, 0.3);
  color: #ffc107;
}

.dark .notification-info {
  background: rgba(23, 162, 184, 0.2);
  border-color: rgba(23, 162, 184, 0.3);
  color: #17a2b8;
}

.dark .notification-close:hover {
  background: rgba(255, 255, 255, 0.1);
}

</style>

<style scoped>
/* 移动端响应式设计 */
@media (max-width: 768px) {
  .task-list-view {
    padding: 15px;
  }

  h1 {
    font-size: 1.5em;
    margin-bottom: 20px;
  }

  .filter-controls {
    flex-direction: column;
    align-items: stretch;
    gap: 15px;
  }

  .search-section {
    margin-bottom: 15px;
  }

  .search-input-container {
    max-width: none;
    width: 100%;
  }

  .action-controls {
    flex-direction: column;
    gap: 8px;
  }


  .status-filters {
    justify-content: center;
  }

  .filter-button {
    padding: 6px 12px;
    font-size: 0.85em;
  }

  .task-card {
    padding: 12px;
    width: 100%;
    max-width: 100%;
    box-sizing: border-box;
    overflow: hidden;
  }

  .task-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .task-header h3 {
    font-size: 1.1em;
  }

  .task-actions {
    flex-direction: column;
    gap: 8px;
  }

  .log-button, .stop-button {
    width: 100%;
    justify-content: center;
  }

  .task-log-container {
    margin-top: 12px;
  }

  .task-log-header {
    padding: 10px 12px;
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .log-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .copy-log-button, .close-log-button {
    padding: 5px 8px;
    font-size: 0.75em;
  }

  .task-log-content {
    max-height: 300px;
  }

  .log-text {
    padding: 12px;
    font-size: 0.85em;
    line-height: 1.4;
  }

  .pagination {
    flex-direction: column;
    gap: 8px;
  }

  .page-numbers {
    justify-content: center;
    flex-wrap: wrap;
  }

  .page-number {
    padding: 6px 10px;
    min-width: 35px;
    font-size: 0.85em;
  }

  .page-button {
    padding: 6px 12px;
    font-size: 0.85em;
  }

  .refresh-button {
    width: 100%;
    justify-content: center;
  }
}

/* 深色模式适配 */
.dark h1, .dark h2 {
  color: var(--text-color-light);
}

.dark .task-card {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.05) 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  overflow: hidden;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3), 0 1px 3px rgba(0, 0, 0, 0.4);
}

.dark .task-card::before {
  background: linear-gradient(90deg, #007bff 0%, #28a745 50%, #6f42c1 100%);
}

.dark .task-card:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.08) 100%);
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
  transform: translateY(-3px);
}

.dark .task-header h3 {
  color: var(--text-color-light);
}

.dark .task-id-subtitle {
  color: var(--text-color-light);
}

.dark .filter-controls {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: var(--border-color);
}

.dark .search-input {
  background-color: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .search-input:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.3);
}

.dark .clear-search-button {
  color: var(--text-color-light);
}

.dark .clear-search-button:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.dark .filter-button {
  background-color: rgba(255, 255, 255, 0.1);
  color: var(--text-color-light);
  border-color: var(--border-color);
}

.dark .filter-button:hover {
  background-color: rgba(255, 255, 255, 0.2);
}

.dark .filter-button.active {
  background-color: var(--primary-color);
  color: var(--white-color);
}

.dark .task-stats {
  background-color: rgba(255, 255, 255, 0.05);
  color: var(--text-color-light);
}

.dark .task-log-container {
  background-color: rgba(255, 255, 255, 0.05);
  border-color: rgba(255, 255, 255, 0.1);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
}

.dark .task-log-header {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.1);
}

.dark .task-log-header h4 {
  color: var(--text-color-light);
}

.dark .copy-log-button, .dark .close-log-button {
  background-color: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .copy-log-button:hover {
  background-color: #007bff;
  border-color: #007bff;
}

.dark .close-log-button:hover {
  background-color: #dc3545;
  border-color: #dc3545;
}

.dark .log-text {
  background-color: rgba(255, 255, 255, 0.03);
  color: var(--text-color-light);
}

.dark .task-log-content::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
}

.dark .task-log-content::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
}

.dark .task-log-content::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
}

.dark .progress-bar {
  background-color: rgba(255, 255, 255, 0.1);
}

.dark .progress-info {
  color: var(--text-color-light);
}

.dark .page-ellipsis {
  color: var(--text-color-light);
}

.dark .page-button {
  background-color: rgba(255, 255, 255, 0.1);
  color: var(--text-color-light);
  border-color: var(--border-color);
}

.dark .page-button:hover:not(:disabled) {
  background-color: rgba(255, 255, 255, 0.2);
  border-color: var(--border-color);
}

.dark .page-button:disabled {
  background-color: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.5);
  border-color: var(--border-color);
}

.dark .page-number {
  background-color: rgba(255, 255, 255, 0.1);
  color: var(--text-color-light);
  border-color: var(--border-color);
}

.dark .page-number:hover {
  background-color: rgba(255, 255, 255, 0.2);
  border-color: var(--border-color);
}

.dark .page-number.active {
  background-color: var(--primary-color);
  color: var(--white-color);
  border-color: var(--primary-color);
}

.dark .page-number:disabled {
  background-color: rgba(255, 255, 255, 0.05);
  color: rgba(255, 255, 255, 0.5);
  border: none;
}


.dark .clear-button {
  background-color: rgba(220, 53, 69, 0.8);
  color: var(--text-color-light);
}

.dark .clear-button:hover:not(:disabled) {
  background-color: rgba(195, 50, 64, 0.8);
}

.dark .log-button {
  background-color: #007bff;
  color: white;
}

.dark .log-button:hover {
  background-color: #0056b3;
}

.dark .stop-button {
  background-color: #dc3545;
  color: white;
}

.dark .stop-button:hover {
  background-color: #c82333;
}

.dark .retry-button {
  background-color: #28a745;
  color: white;
}

.dark .retry-button:hover {
  background-color: #1e7e34;
}

.dark .gallery-button {
  background-color: #6f42c1;
  color: white;
}

.dark .gallery-button:hover {
  background-color: #5a359a;
}

.dark .info-message {
  background-color: rgba(255, 255, 255, 0.05);
  color: var(--text-color-light);
  border-color: var(--border-color);
}

.dark .loading-message {
  background-color: rgba(255, 255, 255, 0.05);
  color: var(--text-color-light);
  border-color: var(--border-color);
}

/* 深色模式确认对话框样式 */
.confirm-dialog-modal.dark-modal {
  background: rgba(0, 0, 0, 0.7) !important;
}

.confirm-dialog.dark-dialog {
  background: rgba(33, 37, 41, 0.95) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  color: #ffffff !important;
}

.confirm-dialog.dark-dialog h3 {
  color: #ffffff !important;
}

.confirm-dialog.dark-dialog p {
  color: #ffffff !important;
}

.confirm-dialog.dark-dialog button {
  background: rgba(255, 255, 255, 0.1) !important;
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  color: #ffffff !important;
}

.confirm-dialog.dark-dialog button:hover {
  background: rgba(255, 255, 255, 0.2) !important;
}

.confirm-dialog.dark-dialog #confirm-btn {
  background: rgba(220, 53, 69, 0.8) !important;
  border-color: rgba(220, 53, 69, 0.8) !important;
}

.confirm-dialog.dark-dialog #confirm-btn:hover {
  background: rgba(220, 53, 69, 0.9) !important;
}
</style>

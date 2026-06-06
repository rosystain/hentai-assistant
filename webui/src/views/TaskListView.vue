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
            <!-- 右上角更多操作菜单 -->
            <div class="task-more-menu" v-if="task.status !== '进行中'">
              <button class="more-btn" @click.stop="openMenuId = openMenuId === task.id ? null : task.id">⋮</button>
              <div class="more-dropdown" v-show="openMenuId === task.id">
                <button
                  @click.stop="confirmDeleteTask(task); openMenuId = null;"
                  :disabled="deletingTasks[task.id]"
                  class="dropdown-item delete-text"
                >
                  {{ deletingTasks[task.id] ? '删除中...' : '🗑️ 删除任务' }}
                </button>
              </div>
            </div>

            <!-- 封面 + 元数据两栏布局 -->
            <div class="task-body" :class="{ 'has-cover': task.cover_url }">
              <div v-if="task.cover_url" class="task-cover">
                <img :src="task.cover_url" alt="cover" loading="lazy" />
              </div>
              <div class="task-info">
                <h4 class="task-display-title" :title="task.filename || '未知文件名'">
                  {{ formatFilename(task.filename) || '未知文件名' }}
                </h4>
                <p class="task-id-subtitle">
                  任务ID: {{ task.id }}
                  <span :class="['status-badge-inline', statusClass(task.status)]">{{ statusText(task.status) }}</span>
                </p>
                <div v-if="task.comicinfo && (task.comicinfo.Genre || task.comicinfo.LanguageISO || task.comicinfo.AgeRating || task.comicinfo.Translator)" class="task-capsules">
                  <template v-if="task.comicinfo.Genre">
                    <span v-for="(g, idx) in String(task.comicinfo.Genre).split(',')" :key="'genre-'+idx" class="capsule capsule-genre" v-show="g.trim()">
                      {{ g.trim() }}
                    </span>
                  </template>
                  <template v-if="task.comicinfo.AgeRating">
                    <span class="capsule capsule-age">{{ task.comicinfo.AgeRating }}</span>
                  </template>
                  <template v-if="task.comicinfo.LanguageISO">
                    <span class="capsule capsule-lang" :title="task.comicinfo.LanguageISO">{{ getNativeLanguageName(task.comicinfo.LanguageISO) }}</span>
                  </template>
                  <template v-if="task.comicinfo.Translator">
                    <span v-for="(t, idx) in String(task.comicinfo.Translator).split(',')" :key="'trans-'+idx" class="capsule capsule-trans" v-show="t.trim()">
                      {{ t.trim() }}
                    </span>
                  </template>
                </div>
                <p v-if="task.comicinfo && task.comicinfo.Series" class="task-filename-subtitle" :title="`${task.comicinfo.Series}${task.comicinfo.Number ? ' #' + task.comicinfo.Number : ''}`">
                  {{ task.comicinfo.Series }}{{ task.comicinfo.Number ? ` #${task.comicinfo.Number}` : '' }}
                </p>
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
                    v-if="task.status === '完成' && task.output_path"
                    @click="toggleEditPanel(task)"
                    class="edit-button"
                  >
                    {{ editingTasks[task.id] ? '关闭编辑' : '编辑文件' }}
                  </button>
                  <button
                    v-if="task.has_path_difference"
                    @click="showMoveDialog(task)"
                    :disabled="movingTasks[task.id]"
                    class="move-button"
                    title="移动文件到符合命名模板的新位置"
                  >
                    {{ movingTasks[task.id] ? '移动中...' : '移动文件' }}
                  </button>
                  <button
                    v-if="task.status === '错误' || task.status === '取消'"
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


              </div>
            </div>

            <!-- 操作状态指示器 -->
            <div v-if="(task.repack_status && task.repack_status !== 'completed') || (task.move_status && task.move_status !== 'completed') || task.last_error" class="task-operation-status">
              <span v-if="task.repack_status && task.repack_status !== 'completed'" :class="['op-status-badge', `op-status-${task.repack_status}`]">
                📦 打包: {{ formatOpStatus(task.repack_status) }}
              </span>
              <span v-if="task.move_status && task.move_status !== 'completed'" :class="['op-status-badge', `op-status-${task.move_status}`]">
                📁 移动: {{ formatOpStatus(task.move_status) }}
              </span>
              <span v-if="task.last_error" class="op-status-error-msg" :title="task.last_error">
                ⚠️ {{ task.last_error }}
              </span>
            </div>

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


            <!-- 元数据编辑面板 -->
            <div v-if="editingTasks[task.id]" class="edit-panel">
              <div class="edit-panel-header">
                <h4 class="edit-panel-title">编辑 ComicInfo 元数据</h4>
                <div class="edit-panel-actions">
                  <button v-if="task.output_path" class="path-button" :title="task.output_path" @click="copyPath(task.output_path)">
                    📁 路径
                  </button>
                  <button v-if="task.metadata" class="path-button" title="点击复制原始元数据 JSON" @click="copyRawMetadata(task.metadata, task.id)">
                    📄 元数据
                  </button>
                </div>
              </div>
              <div class="edit-form">
                <div class="edit-field">
                  <label>Title</label>
                  <input type="text" v-model="editForms[task.id].Title" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Title') }" />
                </div>
                <div class="edit-field">
                  <label>Series</label>
                  <input type="text" v-model="editForms[task.id].Series" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Series') }" />
                </div>
                <div class="edit-field-row">
                  <div class="edit-field">
                    <label>Number</label>
                    <input type="text" v-model="editForms[task.id].Number" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Number') }" />
                  </div>
                  <div class="edit-field">
                    <label>LanguageISO</label>
                    <input type="text" v-model="editForms[task.id].LanguageISO" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'LanguageISO') }" />
                  </div>
                </div>
                <div class="edit-field-row">
                  <div class="edit-field">
                    <label>Writer</label>
                    <input type="text" v-model="editForms[task.id].Writer" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Writer') }" />
                  </div>
                  <div class="edit-field">
                    <label>Penciller</label>
                    <input type="text" v-model="editForms[task.id].Penciller" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Penciller') }" />
                  </div>
                </div>
                <div class="edit-field">
                  <label>Tags</label>
                  <textarea v-model="editForms[task.id].Tags" rows="2" placeholder="逗号分隔" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Tags') }"></textarea>
                </div>
                <div class="edit-field-row">
                  <div class="edit-field">
                    <label>Genre</label>
                    <input type="text" v-model="editForms[task.id].Genre" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Genre') }" />
                  </div>
                  <div class="edit-field">
                    <label>Translator</label>
                    <input type="text" v-model="editForms[task.id].Translator" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Translator') }" />
                  </div>
                </div>
                <div class="edit-field-row">
                  <div class="edit-field">
                    <label>AgeRating</label>
                    <input type="text" v-model="editForms[task.id].AgeRating" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'AgeRating') }" />
                  </div>
                  <div class="edit-field">
                    <label>Manga</label>
                    <select v-model="editForms[task.id].Manga" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Manga') }">
                      <option value="">未设置</option>
                      <option value="YesAndRightToLeft">从右到左</option>
                      <option value="Yes">从左到右</option>
                      <option value="No">否</option>
                    </select>
                  </div>
                </div>
                <div class="edit-field-row">
                  <div class="edit-field">
                    <label>AlternateSeries</label>
                    <input type="text" v-model="editForms[task.id].AlternateSeries" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'AlternateSeries') }" />
                  </div>
                  <div class="edit-field">
                    <label>AlternateNumber</label>
                    <input type="text" v-model="editForms[task.id].AlternateNumber" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'AlternateNumber') }" />
                  </div>
                </div>
                <div class="edit-field">
                  <label>SeriesGroup</label>
                  <input type="text" v-model="editForms[task.id].SeriesGroup" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'SeriesGroup') }" />
                </div>
                <div class="edit-field">
                  <label>Summary</label>
                  <textarea v-model="editForms[task.id].Summary" rows="3" :class="{ 'diff-highlight': isFieldDifferent(task.id, 'Summary') }"></textarea>
                </div>
              </div>
              <div class="edit-actions">
                <button
                  @click="generateFromMetadata(task.id)"
                  class="read-button"
                  title="使用 Metadata 重新构建 ComicInfo"
                >
                  读取元数据
                </button>
                <button
                  @click="readFromCbz(task.id)"
                  :disabled="readingCbz[task.id]"
                  class="read-button"
                  title="加载压缩包中的 ComicInfo.xml"
                >
                  {{ readingCbz[task.id] ? '读取中...' : '读取压缩包' }}
                </button>
                <button
                  @click="saveMetadata(task.id)"
                  :disabled="savingMetadata[task.id] || !hasAnyFieldChanged(task.id)"
                  class="save-button"
                  :title="!hasAnyFieldChanged(task.id) ? '未检测到修改' : ''"
                >
                  {{ savingMetadata[task.id] ? '保存中...' : '保存修改' }}
                </button>
              </div>
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
  metadata?: Record<string, any> | null;
  comicinfo?: Record<string, any> | null;
  output_path?: string | null;
  target_path?: string | null;
  cover_url?: string | null;
  pending_changes?: Record<string, any> | null;
  repack_status?: string | null;
  move_status?: string | null;
  last_error?: string | null;
  has_path_difference?: boolean;
}

const tasks = ref<Task[]>([]);
const loading = ref(true);
const refreshing = ref(false); // 新增：自动刷新状态
const error = ref<string | null>(null);
const expandedLogs = ref<{ [key: string]: boolean }>({});
const stoppingTasks = ref<{ [key: string]: boolean }>({});
const retryingTasks = ref<{ [key: string]: boolean }>({});
const deletingTasks = ref<{ [key: string]: boolean }>({});

const currentFilter = ref<string>('all'); // 当前选中的过滤器
const clearing = ref(false); // 清除任务状态
const searchQuery = ref<string>(''); // 搜索查询
let searchTimeout: number | null = null;
const openMenuId = ref<string | null>(null); // 控制哪个任务的更多菜单打开
let refreshInterval: number | undefined;
let refreshTimeout: number | undefined;
const { isDark } = useTheme();

// 元数据编辑相关状态
const editingTasks = ref<{ [key: string]: boolean }>({});
const editForms = ref<{ [key: string]: Record<string, any> }>({});
const savingMetadata = ref<{ [key: string]: boolean }>({});
const readingCbz = ref<{ [key: string]: boolean }>({});
const movingTasks = ref<{ [key: string]: boolean }>({});

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

// 分页后的任务列表（不再前端过滤，直接返回后端分页后的结果）
const paginatedTasks = computed(() => {
  return tasks.value;
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
    
    if (searchQuery.value.trim()) {
      params.append('search', searchQuery.value.trim());
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
const showConfirmDialog = (message: string, options?: { showDeleteFileOption?: boolean }): Promise<boolean | 'delete_file'> => {
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
    buttonContainer.style.cssText = 'display: flex; justify-content: space-between; align-items: center; width: 100%;';

    const leftContainer = document.createElement('div');
    const rightContainer = document.createElement('div');
    rightContainer.style.cssText = 'display: flex; gap: 12px;';

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

    rightContainer.appendChild(cancelBtn);
    rightContainer.appendChild(confirmBtn);

    let isDeleteFileChecked = false;

    if (options?.showDeleteFileOption) {
      const label = document.createElement('label');
      label.style.cssText = `
        display: flex;
        align-items: center;
        gap: 8px;
        cursor: pointer;
        color: ${isDark ? '#aaa' : '#888'};
        font-size: 0.9em;
        user-select: none;
        margin: 0;
      `;
      
      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.style.cssText = 'cursor: pointer; width: 16px; height: 16px; margin: 0;';
      checkbox.onchange = (e) => {
        isDeleteFileChecked = (e.target as HTMLInputElement).checked;
      };

      const textSpan = document.createElement('span');
      textSpan.textContent = '连同物理文件一起删除';

      label.appendChild(checkbox);
      label.appendChild(textSpan);
      leftContainer.appendChild(label);
    }

    buttonContainer.appendChild(leftContainer);
    buttonContainer.appendChild(rightContainer);
    buttonContainer.style.marginTop = '20px';
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

    confirmBtn?.addEventListener('click', async () => {
      if (options?.showDeleteFileOption && isDeleteFileChecked) {
        modal.style.display = 'none';
        const doubleConfirm = await showConfirmDialog('⚠️ 警告：您勾选了连同文件系统中的物理文件一起删除。\n此操作将永久从硬盘中抹除文件且不可恢复。\n\n确定要彻底删除吗？');
        if (doubleConfirm === true) {
          cleanup();
          resolve('delete_file');
        } else {
          modal.style.display = 'flex';
        }
      } else {
        cleanup();
        resolve(true);
      }
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

const copyPath = (path: string | null) => {
  if (!path) return;
  showCopyModal(path);
};

const copyRawMetadata = (metadata: Record<string, any> | null | undefined, taskId: string) => {
  if (!metadata) return;
  showCopyModal(JSON.stringify(metadata, null, 2), { isMetadata: true, taskId });
};

const copyLog = (logContent: string | null) => {
  if (!logContent) {
    showNotification('没有日志内容可复制', 'warning');
    return;
  }
  showCopyModal(logContent);
};

// 显示复制模态框的辅助函数
const showCopyModal = (content: string, options?: { isMetadata?: boolean, taskId?: string }) => {
  const isDark = document.documentElement.classList.contains('dark');

  const modal = document.createElement('div');
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
    z-index: 10000;
  `;

  const dialog = document.createElement('div');
  dialog.style.cssText = `
    background: ${isDark ? '#212529' : 'white'};
    border: ${isDark ? '1px solid rgba(255, 255, 255, 0.2)' : 'none'};
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
  // title.textContent = '查看元数据';
  title.style.cssText = `margin: 0 0 16px 0; color: ${isDark ? '#ffffff' : '#333'}; font-size: 18px;`;

  // 创建说明文本
  const description = document.createElement('p');
  description.style.cssText = `margin: 0 0 16px 0; color: ${isDark ? '#adb5bd' : '#666'}; font-size: 14px;`;

  header.appendChild(title);
  header.appendChild(description);

  const textarea = document.createElement('textarea');
  textarea.value = content;
  textarea.style.cssText = `
    width: 100%;
    height: 300px;
    border: 2px solid ${isDark ? 'rgba(13, 110, 253, 0.5)' : '#007bff'};
    border-radius: 6px;
    padding: 12px;
    font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', monospace;
    font-size: 13px;
    line-height: 1.4;
    resize: vertical;
    background: ${isDark ? '#2b3035' : '#f8f9fa'};
    color: ${isDark ? '#f8f9fa' : '#212529'};
    margin-bottom: 16px;
  `;
  textarea.readOnly = true;

  const buttonContainer = document.createElement('div');
  buttonContainer.style.cssText = `
    display: flex;
    justify-content: space-between;
  `;

  const leftBtns = document.createElement('div');
  leftBtns.style.cssText = `display: flex; gap: 8px;`;

  const rightBtns = document.createElement('div');
  rightBtns.style.cssText = `display: flex; gap: 8px;`;

  if (options?.isMetadata && options.taskId) {
      const refreshBtn = document.createElement('button');
      refreshBtn.textContent = '刷新元数据';
      refreshBtn.style.cssText = `
        padding: 8px 16px;
        background: ${isDark ? 'rgba(25, 135, 84, 0.8)' : '#198754'};
        color: white;
        border: ${isDark ? '1px solid rgba(25, 135, 84, 0.8)' : 'none'};
        border-radius: 4px;
        cursor: pointer;
        font-size: 14px;
      `;
      
      refreshBtn.onclick = async () => {
          refreshBtn.disabled = true;
          refreshBtn.textContent = '获取中...';
          const originalValue = textarea.value;
          textarea.value = "正在从网络重新获取最新 gmetadata.json，请稍候...";
          try {
              const response = await axios.post(`${API_BASE_URL}/tasks/${options.taskId}/refresh-gmetadata`);
              showNotification('成功获取最新元数据', 'success');
              const newMetadata = response.data.task.metadata;
              textarea.value = JSON.stringify(newMetadata, null, 2);
              
              // 同步更新 tasks 列表中的数据
              const taskIndex = tasks.value.findIndex((t: any) => t.id === options.taskId);
              if (taskIndex !== -1) {
                  tasks.value[taskIndex].metadata = newMetadata;
              }
          } catch (err: any) {
              const errMsg = err.response?.data?.error || err.message;
              showNotification(`获取失败: ${errMsg}`, 'error');
              textarea.value = `${originalValue}\n\n[错误] 获取失败: ${errMsg}`;
          } finally {
              refreshBtn.disabled = false;
              refreshBtn.textContent = '重新获取';
          }
      };
      leftBtns.appendChild(refreshBtn);
  }

  const selectAllBtn = document.createElement('button');
  selectAllBtn.textContent = '全选';
  selectAllBtn.style.cssText = `
    padding: 8px 16px;
    background: ${isDark ? 'rgba(255, 255, 255, 0.1)' : '#6c757d'};
    color: ${isDark ? '#ffffff' : 'white'};
    border: ${isDark ? '1px solid rgba(255, 255, 255, 0.2)' : 'none'};
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
    background: ${isDark ? 'rgba(13, 110, 253, 0.8)' : '#007bff'};
    color: white;
    border: ${isDark ? '1px solid rgba(13, 110, 253, 0.8)' : 'none'};
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

  rightBtns.appendChild(selectAllBtn);
  rightBtns.appendChild(closeBtn);
  
  buttonContainer.appendChild(leftBtns);
  buttonContainer.appendChild(rightBtns);
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
    await axios.post(`${API_BASE_URL}/tasks/${taskId}/cancel`);
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
    const response = await axios.post(`${API_BASE_URL}/tasks/${taskId}/retry`);

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

const confirmDeleteTask = async (task: any) => {
  const hasOutput = !!task.output_path;
  const result = await showConfirmDialog('确定要删除此任务记录吗？此操作不可撤销。', { showDeleteFileOption: hasOutput });
  if (result === 'delete_file') {
    deleteTask(task.id, true);
  } else if (result === true) {
    deleteTask(task.id, false);
  }
};

const deleteTask = async (taskId: string, deleteFile: boolean = false) => {
  deletingTasks.value[taskId] = true;
  try {
    await axios.delete(`${API_BASE_URL}/tasks/${taskId}`, {
      params: { delete_file: deleteFile }
    });
    showNotification(deleteFile ? '任务记录及物理文件已彻底删除' : '任务记录已删除', 'success');
    await fetchTasks(false);
  } catch (err: any) {
    console.error(`删除任务 ${taskId} 失败:`, err);
    showNotification(`删除任务失败: ${err.response?.data?.message || err.message}`, 'error');
  } finally {
    deletingTasks.value[taskId] = false;
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

  return formatted;
};

const formatMetadataTitle = (metadata: Record<string, any>): string => {
  const titleJpn = metadata.title_jpn;
  const title = metadata.title;
  if (titleJpn && title) {
    return `${title} / ${titleJpn}`;
  }
  return titleJpn || title || '未知';
};

const formatTagPreview = (tags: any[]): string => {
  if (!Array.isArray(tags) || tags.length === 0) return '';
  const preview = tags.slice(0, 6).join(', ');
  return tags.length > 6 ? `${preview} ... (${tags.length})` : preview;
};

const getDisplayTags = (tagsStr: string | null | undefined): string[] => {
  if (!tagsStr) return [];
  return tagsStr.split(',').map(t => t.trim()).filter(t => t);
};

const LANGUAGE_MAP: Record<string, string> = {
  'zh': 'Chinese',
  'en': 'English',
  'ja': 'Japanese',
  'ko': 'Korean',
  'fr': 'French',
  'es': 'Spanish',
  'ru': 'Russian',
  'de': 'German',
  'it': 'Italian',
  'vi': 'Vietnamese',
  'th': 'Thai',
  'pt': 'Portuguese',
  'id': 'Indonesian',
  'ar': 'Arabic'
};

const getLanguageDisplay = (langCode: string | null | undefined): string => {
  if (!langCode) return '';
  const code = langCode.toLowerCase().trim();
  // Handle some common variations like zh-cn
  if (code.startsWith('zh')) return 'Chinese';
  return LANGUAGE_MAP[code] || langCode;
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
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  searchTimeout = window.setTimeout(() => {
    pagination.value.page = 1;
    fetchTasks(true);
    updateUrlQuery();
  }, 500);
};

// 清除搜索
const clearSearch = () => {
  searchQuery.value = '';
  pagination.value.page = 1;
  fetchTasks(true);
  updateUrlQuery();
};

const updateUrlQuery = () => {
  const url = new URL(window.location.href);
  if (searchQuery.value.trim()) {
    url.searchParams.set('search', searchQuery.value.trim());
  } else {
    url.searchParams.delete('search');
  }
  window.history.replaceState({}, '', url);
};

const checkUrlQuery = () => {
  const urlParams = new URLSearchParams(window.location.search);
  const searchParam = urlParams.get('search');
  // 也支持传入 url 参数进行反查，直接作为 search 词
  const urlParam = urlParams.get('url');
  
  if (searchParam) {
    searchQuery.value = searchParam;
  } else if (urlParam) {
    searchQuery.value = urlParam;
  }
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
    statusToClear = 'completed';
    statusName = '已完成';
  } else if (currentFilter.value === 'cancelled') {
    statusToClear = 'cancelled';
    statusName = '取消';
  } else if (currentFilter.value === 'failed') {
    statusToClear = 'failed';
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
    await axios.post(`${API_BASE_URL}/tasks/clear?status=${status}`);
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

// 切换编辑面板
const toggleEditPanel = (task: Task) => {
  const taskId = task.id;
  if (editingTasks.value[taskId]) {
    editingTasks.value[taskId] = false;
    return;
  }

  // 初始化编辑表单：优先 comicinfo，回退 metadata
  const metaFinal = task.comicinfo;
  const metaRaw = task.metadata;

  if (metaFinal && Object.keys(metaFinal).length > 0) {
    // 从 ComicInfo (comicinfo) 预填
    editForms.value[taskId] = {
      Title: metaFinal.Title || '',
      Series: metaFinal.Series || '',
      Number: metaFinal.Number || '',
      Writer: metaFinal.Writer || '',
      Penciller: metaFinal.Penciller || '',
      Tags: metaFinal.Tags || '',
      LanguageISO: metaFinal.LanguageISO || '',
      Genre: metaFinal.Genre || '',
      Translator: metaFinal.Translator || '',
      AgeRating: metaFinal.AgeRating || '',
      Manga: metaFinal.Manga || '',
      AlternateSeries: metaFinal.AlternateSeries || '',
      AlternateNumber: metaFinal.AlternateNumber || '',
      SeriesGroup: metaFinal.SeriesGroup || '',
      Summary: metaFinal.Summary || '',
    };
  } else if (metaRaw) {
    // 回退：从 gmetadata (metadata) 提取基本信息
    const rawTitle = metaRaw.title_jpn || metaRaw.title || '';
    const extractedSeries = metaRaw.Series || '';
    const extractedNumber = metaRaw.Number || '';
    editForms.value[taskId] = {
      Title: rawTitle,
      Series: extractedSeries,
      Number: extractedNumber,
      Writer: '',
      Penciller: '',
      Tags: Array.isArray(metaRaw.tags) ? metaRaw.tags.join(', ') : '',
      LanguageISO: '',
      Genre: metaRaw.category?.toLowerCase() !== 'non-h' ? 'Hentai' : '',
      Translator: '',
      AgeRating: 'R18+',
      Manga: 'YesAndRightToLeft',
      AlternateSeries: extractedSeries,
      AlternateNumber: extractedNumber,
      SeriesGroup: '',
      Summary: '',
    };
  } else {
    editForms.value[taskId] = {
      Title: '', Series: '', Number: '', Writer: '', Penciller: '',
      Tags: '', LanguageISO: '', Genre: '', Translator: '', AgeRating: '', Manga: '',
      AlternateSeries: '', AlternateNumber: '', SeriesGroup: '', Summary: '',
    };
  }
  editingTasks.value[taskId] = true;
};

// 从 metadata 生成表单数据
const generateFromMetadata = async (taskId: string) => {
  savingMetadata.value[taskId] = true; // 复用 savingMetadata 来显示加载状态，或者你可以新增一个 loading 状态
  try {
    const response = await axios.get(`${API_BASE_URL}/tasks/${taskId}/generate-comicinfo`);
    if (response.data.comicinfo) {
      const cbzMeta = response.data.comicinfo;
      
      editForms.value[taskId] = {
        Title: cbzMeta.Title || '',
        Series: cbzMeta.Series || '',
        Number: cbzMeta.Number || '',
        Writer: cbzMeta.Writer || '',
        Penciller: cbzMeta.Penciller || '',
        Tags: cbzMeta.Tags || '',
        LanguageISO: cbzMeta.LanguageISO || '',
        Genre: cbzMeta.Genre || '',
        Translator: cbzMeta.Translator || '',
        AgeRating: cbzMeta.AgeRating || '',
        Manga: cbzMeta.Manga || '',
        AlternateSeries: cbzMeta.AlternateSeries || '',
        AlternateNumber: cbzMeta.AlternateNumber || '',
        SeriesGroup: cbzMeta.SeriesGroup || '',
        Summary: cbzMeta.Summary || '',
      };
      showNotification('已从原始 metadata 重新生成并填充数据，请检查红字差异', 'success');
    }
  } catch (err: any) {
    console.error(`从 metadata 生成失败:`, err);
    showNotification(`生成失败: ${err.response?.data?.error || err.message}`, 'error');
  } finally {
    savingMetadata.value[taskId] = false;
  }
};

// 从物理文件读取元数据
const readFromCbz = async (taskId: string) => {
  readingCbz.value[taskId] = true;
  try {
    const response = await axios.post(`${API_BASE_URL}/tasks/${taskId}/read-cbz`);
    showNotification('成功读取并更新数据库', 'success');

    if (response.data.comicinfo) {
      const cbzMeta = response.data.comicinfo;
      
      editForms.value[taskId] = {
        Title: cbzMeta.Title || '',
        Series: cbzMeta.Series || '',
        Number: cbzMeta.Number || '',
        Writer: cbzMeta.Writer || '',
        Penciller: cbzMeta.Penciller || '',
        Tags: cbzMeta.Tags || '',
        LanguageISO: cbzMeta.LanguageISO || '',
        Genre: cbzMeta.Genre || '',
        Translator: cbzMeta.Translator || '',
        AgeRating: cbzMeta.AgeRating || '',
        Manga: cbzMeta.Manga || '',
        AlternateSeries: cbzMeta.AlternateSeries || '',
        AlternateNumber: cbzMeta.AlternateNumber || '',
        SeriesGroup: cbzMeta.SeriesGroup || '',
        Summary: cbzMeta.Summary || '',
      };

      // 更新本地任务数据，消除标红差异
      if (response.data.task) {
        const index = tasks.value.findIndex(t => t.id === taskId);
        if (index !== -1) {
          tasks.value[index] = { ...tasks.value[index], ...response.data.task };
        }
      }
    }
  } catch (err: any) {
    console.error(`读取文件失败:`, err);
    showNotification(`读取文件失败: ${err.response?.data?.error || err.message}`, 'error');
  } finally {
    readingCbz.value[taskId] = false;
  }
};

// 检查表单是否有任何未保存的修改
const hasAnyFieldChanged = (taskId: string) => {
  const fieldsToCheck = [
    'Title', 'Series', 'Number', 'LanguageISO', 'Writer', 'Penciller', 
    'Tags', 'Genre', 'Translator', 'AgeRating', 'Manga', 'AlternateSeries', 
    'AlternateNumber', 'SeriesGroup', 'Summary'
  ];
  return fieldsToCheck.some(field => isFieldDifferent(taskId, field));
};

// 检查当前表单值与数据库原始值是否有差异
const isFieldDifferent = (taskId: string, fieldName: string) => {
  const task = tasks.value.find(t => t.id === taskId);
  if (!task || !editingTasks.value[taskId]) return false;
  
  let metaFinal: any = {};
  try {
    metaFinal = typeof task.comicinfo === 'string' 
      ? JSON.parse(task.comicinfo) 
      : (task.comicinfo || {});
  } catch (e) {}

  // 特殊处理未设置的情况，统一视作空字符串
  const originalValue = String(metaFinal[fieldName] || '').trim();
  const currentValue = String(editForms.value[taskId]?.[fieldName] || '').trim();
  return originalValue !== currentValue;
};

// 保存元数据
const saveMetadata = async (taskId: string) => {
  savingMetadata.value[taskId] = true;
  try {
    // 构建要保存的元数据，过滤掉空值
    const formData = editForms.value[taskId];
    const metadata: Record<string, any> = {};
    for (const [key, value] of Object.entries(formData)) {
      if (value !== null && value !== undefined && value !== '') {
        metadata[key] = value;
      }
    }

    const response = await axios.patch(`${API_BASE_URL}/tasks/${taskId}/metadata`, metadata);
    showNotification('元数据已保存', 'success');

    // 更新本地任务数据
    if (response.data.task) {
      const index = tasks.value.findIndex(t => t.id === taskId);
      if (index !== -1) {
        tasks.value[index] = { ...tasks.value[index], ...response.data.task };
      }
    }
  } catch (err: any) {
    console.error(`保存元数据失败:`, err);
    showNotification(`保存失败: ${err.response?.data?.error || err.message}`, 'error');
  } finally {
    savingMetadata.value[taskId] = false;
  }
};

// 显示移动对话框
const showMoveDialog = async (task: Task) => {
  movingTasks.value[task.id] = true;
  try {
    // 1. 获取后端渲染出来的建议归类新路径
    const response = await axios.get(`${API_BASE_URL}/tasks/${task.id}/move-path`);
    const { current_path, suggested_path, has_difference } = response.data;
    
    if (!suggested_path) {
      showNotification('未能根据配置渲染归类路径，请检查 MOVE_PATH 配置。', 'error');
      return;
    }
    
    if (!has_difference) {
      alert(`当前文件位置已符合归档配置，无需移动。\n\n当前路径：\n${current_path}`);
      return;
    }
    
    // 2. 路径不一致，提示确认
    const confirmed = confirm(
      `检测到归类路径差异。是否将文件移动到新的归档位置？\n\n当前路径：\n${current_path}\n\n新归档路径：\n${suggested_path}`
    );
    
    if (confirmed) {
      await moveTaskFile(task.id, suggested_path);
    }
  } catch (err: any) {
    console.error(`获取移动建议路径失败:`, err);
    showNotification(`获取建议移动路径失败: ${err.response?.data?.error || err.message}`, 'error');
  } finally {
    movingTasks.value[task.id] = false;
  }
};

// 移动文件
const moveTaskFile = async (taskId: string, targetPath?: string) => {
  movingTasks.value[taskId] = true;
  try {
    await axios.post(`${API_BASE_URL}/tasks/${taskId}/move`, { target_path: targetPath });
    showNotification('文件已成功移动归档', 'success');
    await fetchTasks(false);
  } catch (err: any) {
    console.error(`移动文件失败:`, err);
    showNotification(`移动失败: ${err.response?.data?.error || err.message}`, 'error');
  } finally {
    movingTasks.value[taskId] = false;
  }
};

// 格式化操作状态
const formatOpStatus = (status: string): string => {
  switch (status) {
    case 'in_progress': return '进行中...';
    case 'completed': return '完成';
    case 'failed': return '失败';
    default: return status;
  }
};

// Language ISO 映射到本国语言名称
const getNativeLanguageName = (iso: string): string => {
  if (!iso) return '';
  const langMap: Record<string, string> = {
    'zh': '中文',
    'zh-hk': '繁體中文',
    'zh-tw': '繁體中文',
    'en': 'English',
    'ja': '日本語',
    'ko': '한국어',
    'fr': 'Français',
    'de': 'Deutsch',
    'es': 'Español',
    'ru': 'Русский',
    'it': 'Italiano',
    'pt': 'Português',
    'pt-br': 'Português (Brasil)',
    'vi': 'Tiếng Việt',
    'th': 'ไทย',
    'id': 'Bahasa Indonesia',
    'ar': 'العربية'
  };
  return langMap[iso.toLowerCase()] || iso;
};

onMounted(() => {
  checkUrlQuery();
  fetchTasks(true); // 初始加载
  startSmartRefresh(); // 开始智能刷新
  document.addEventListener('click', () => {
    openMenuId.value = null;
  });
});

onUnmounted(() => {
  if (refreshTimeout) {
    clearTimeout(refreshTimeout);
  }
  document.removeEventListener('click', () => {
    openMenuId.value = null;
  });
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
  position: relative;
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
}

/* 更多操作菜单 */
.task-more-menu {
  position: absolute;
  top: 20px; /* 和卡片内边距完美对齐 */
  right: 20px;
  z-index: 10;
}

.more-btn {
  background: transparent;
  border: none;
  font-size: 1.2em;
  line-height: 1;
  color: #aaa;
  cursor: pointer;
  padding: 0;
  padding-bottom: 4px; /* 微调字符垂直居中 (弥补字体基线偏移) */
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
}

.more-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: #333;
}

.more-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  background: white;
  border: 1px solid #eee;
  border-radius: 6px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.1);
  min-width: 120px;
  padding: 4px 0;
  z-index: 20;
}

.dropdown-item {
  display: block;
  width: 100%;
  text-align: left;
  padding: 10px 16px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 0.9em;
  transition: background 0.2s ease;
}

.dropdown-item:hover {
  background: rgba(0, 0, 0, 0.05);
}

.delete-text {
  color: #dc3545;
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

.task-title-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 4px;
  padding-right: 28px;
}

.task-display-title {
  margin: 0;
  padding-right: 28px; /* 避开右上角更多操作按钮 */
  color: #333;
  font-size: clamp(0.95rem, 1vw + 0.4rem, 1.05em); /* 进一步缩小标题字号 */
  font-weight: bold;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

.status-badge-inline {
  font-size: 0.9em;
  padding: 2px 6px;
  border-radius: 4px;
}

.status-success,
.status-cancelled,
.status-error,
.status-in-progress {
  font-weight: bold;
  white-space: nowrap;
  flex-shrink: 0;
}

.task-id-subtitle,
.task-filename-subtitle {
  font-size: 0.85em;
  color: #888;
  margin: 0 0 8px 0;
}

/* 封面 + 元数据两栏布局 */
.task-body {
  display: flex;
  gap: 16px;
  /* margin-top: 12px 已移除，以使海报顶部和卡片顶部 padding(20px) 齐平 */
}

.task-body:not(.has-cover) {
  /* 无封面时元数据占满 */
  display: block;
}

.task-cover {
  flex-shrink: 0;
  width: 155px;
  height: 155px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: transparent;
}

.task-cover img {
  max-width: 100%;
  max-height: 100%;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
}

.task-info {
  flex: 1;
  min-width: 0; /* 防止内容溢出 */
  display: flex;
  flex-direction: column;
}

.task-id-subtitle,
.task-filename-subtitle {
  font-size: 0.85em;
  color: #888;
  margin: 4px 0 4px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.task-filename-subtitle {
  margin-bottom: 8px; /* 给下方 metadata 留出更多空间 */
}

/* 胶囊标签样式 */
.task-capsules {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.capsule {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: 500;
  line-height: 1.2;
}

.capsule-lang,
.capsule-age,
.capsule-trans,
.capsule-genre {
  background: rgba(108, 117, 125, 0.1);
  color: #6c757d;
  border: 1px solid rgba(108, 117, 125, 0.2);
}

.path-button {
  background: rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 0.85em;
  color: #555;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  transition: all 0.2s;
}

.path-button:hover {
  background: rgba(0, 0, 0, 0.1);
  color: #333;
}

.dark .path-button {
  background: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.2);
  color: #ccc;
}

.dark .path-button:hover {
  background: rgba(255, 255, 255, 0.2);
  color: #fff;
}

.task-metadata {
  margin-top: 6px;
  font-size: 0.88em;
  color: #555;
  display: grid;
  gap: 4px;
}
.task-metadata-row {
  display: flex;
  flex-wrap: wrap;
  gap: 2px;
  line-height: 1.5;
}

.task-metadata-label {
  font-weight: 600;
  color: #444;
  margin-right: 6px;
  white-space: nowrap;
}

/* 操作状态指示器 */
.task-operation-status {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  align-items: center;
}

.op-status-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 0.8em;
  font-weight: 500;
}

.op-status-in_progress {
  background: rgba(0, 123, 255, 0.12);
  color: #007bff;
  border: 1px solid rgba(0, 123, 255, 0.3);
}

.op-status-completed {
  background: rgba(40, 167, 69, 0.12);
  color: #28a745;
  border: 1px solid rgba(40, 167, 69, 0.3);
}

.op-status-failed {
  background: rgba(220, 53, 69, 0.12);
  color: #dc3545;
  border: 1px solid rgba(220, 53, 69, 0.3);
}

.op-status-error-msg {
  font-size: 0.8em;
  color: #dc3545;
  max-width: 300px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* 编辑按钮 */
.edit-button {
  padding: 8px 15px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
  background-color: #17a2b8;
  color: white;
}

.edit-button:hover {
  background-color: #138496;
}

/* 编辑面板 */
.edit-panel {
  margin-top: 15px;
  padding: 16px;
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 10px;
  animation: slideDown 0.3s ease-out;
}

.edit-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}

.edit-panel-title {
  margin: 0;
  font-size: 1em;
  font-weight: 600;
  color: #333;
}

.edit-panel-actions {
  display: flex;
  gap: 8px;
}

.edit-panel-actions .path-button {
  margin-left: 0;
}

.edit-form {
  display: grid;
  gap: 10px;
}

.edit-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
}

.edit-field label {
  font-size: 0.82em;
  font-weight: 600;
  color: #555;
}

.edit-field input,
.edit-field textarea,
.edit-field select {
  padding: 7px 10px;
  border: 1px solid #dee2e6;
  border-radius: 5px;
  font-size: 0.9em;
  background: white;
  color: #333;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.edit-field input:focus,
.edit-field textarea:focus,
.edit-field select:focus {
  border-color: #007bff;
  outline: none;
  box-shadow: 0 0 0 0.15rem rgba(0, 123, 255, 0.2);
}

.edit-field textarea {
  resize: vertical;
  font-family: inherit;
}

.edit-field-row {
  display: flex;
  gap: 10px;
}

/* 编辑操作按钮 */
.edit-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.save-button {
  margin-left: auto;
  padding: 8px 16px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
  background: linear-gradient(135deg, #28a745, #20c997);
  color: white;
  font-weight: 500;
}

.save-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #1e7e34, #1baa80);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(40, 167, 69, 0.3);
}

.save-button:disabled {
  background: #cccccc;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.repack-button {
  padding: 8px 16px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
  background: linear-gradient(135deg, #fd7e14, #e65c00);
  color: white;
  font-weight: 500;
}

.repack-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #e65c00, #cc5200);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(253, 126, 20, 0.3);
}

.repack-button:disabled {
  background: #cccccc;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.move-button {
  padding: 8px 16px;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  font-size: 0.9em;
  transition: all 0.3s ease;
  background: linear-gradient(135deg, #6f42c1, #5a2d91);
  color: white;
  font-weight: 500;
}

.move-button:hover:not(:disabled) {
  background: linear-gradient(135deg, #5a2d91, #4a2577);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(111, 66, 193, 0.3);
}

.move-button:disabled {
  background: #cccccc;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.pending-indicator {
  margin-top: 10px;
  padding: 6px 12px;
  background: rgba(255, 193, 7, 0.12);
  border: 1px solid rgba(255, 193, 7, 0.3);
  border-radius: 6px;
  color: #856404;
  font-size: 0.85em;
  font-weight: 500;
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
  margin-top: auto; /* Push to the bottom of flex container */
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.log-button, .stop-button, .retry-button, .gallery-button, .refresh-button, .move-button, .edit-button {
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

.tags-container {
  display: flex;
  flex-wrap: nowrap;
  gap: 6px;
  align-items: center;
  flex: 1;
  overflow-x: auto;
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE/Edge */
  /* 可选：添加右侧淡出效果，让截断更优雅 */
  mask-image: linear-gradient(to right, black 85%, transparent 100%);
  -webkit-mask-image: linear-gradient(to right, black 85%, transparent 100%);
  padding-right: 20px; /* 为淡出留出空间 */
}

.tags-container::-webkit-scrollbar {
  display: none; /* Chrome/Safari/Opera */
}

.tag-capsule {
  display: inline-flex;
  align-items: center;
  padding: 2px 10px;
  background-color: #e9ecef;
  color: #495057;
  border-radius: 12px;
  font-size: 0.85em;
  white-space: nowrap;
  flex-shrink: 0; /* 防止标签被挤压变形 */
}

.dark-theme .tag-capsule,
.dark .tag-capsule {
  background-color: rgba(255, 255, 255, 0.1);
  color: #e0a800;
}

.dark .capsule-lang,
.dark .capsule-age,
.dark .capsule-trans,
.dark .capsule-genre {
  background: rgba(108, 117, 125, 0.2);
  color: #adb5bd;
  border-color: rgba(108, 117, 125, 0.3);
}

/* Edit Panel Dark Mode */
.tag-more {
  font-weight: bold;
  background-color: transparent !important;
  color: #007bff !important;
  padding: 0 4px;
}

.dark-theme .tag-more,
.dark .tag-more {
  color: #63b3ed !important;
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

  .task-body.has-cover {
    flex-direction: column;
    align-items: center;
  }

  .task-cover {
    width: 120px;
    height: 120px;
  }

  .task-cover img {
    max-width: 100%;
    max-height: 100%;
  }

  .task-info {
    width: 100%;
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

  .edit-field-row {
    flex-direction: column;
  }

  .edit-actions {
    flex-direction: column;
  }

  .edit-actions button {
    width: 100%;
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

.dark .more-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  color: #eee;
}

.dark .more-dropdown {
  background: #2a2a2a;
  border-color: #444;
}

.dark .dropdown-item:hover {
  background: rgba(255, 255, 255, 0.08);
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

.dark .task-display-title {
  color: var(--text-color-light);
}

.dark .task-id-subtitle,
.dark .task-filename-subtitle {
  color: var(--text-color-light);
}

.dark .task-metadata {
  color: var(--text-color-light);
}

.dark .edit-panel {
  background: rgba(255, 255, 255, 0.06);
  border-color: rgba(255, 255, 255, 0.12);
}

.dark .edit-panel-title {
  color: var(--text-color-light);
}

.dark .edit-field label {
  color: var(--text-color-light);
}

.dark .edit-field input,
.dark .edit-field textarea,
.dark .edit-field select {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .edit-field input:focus,
.dark .edit-field textarea:focus,
.dark .edit-field select:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 0.15rem rgba(0, 123, 255, 0.3);
}

.dark .edit-button {
  background-color: rgba(23, 162, 184, 0.8);
}

.dark .edit-button:hover {
  background-color: rgba(19, 132, 150, 0.9);
}

.dark .pending-indicator {
  background: rgba(255, 193, 7, 0.15);
  border-color: rgba(255, 193, 7, 0.4);
  color: #ffc107;
}

.dark .op-status-error-msg {
  color: #f58d97;
}

.dark .task-cover img {
  /* border-color removed since border is removed from img */
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


.dark .delete-button:hover {
  background-color: #6c757d;
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

/* 差异高亮效果 */
.diff-highlight {
  border-color: #dc3545 !important;
  outline: 1px solid #dc3545 !important;
  background-color: rgba(220, 53, 69, 0.05) !important;
  box-shadow: 0 0 5px rgba(220, 53, 69, 0.3);
  transition: all 0.3s ease;
}

.dark .diff-highlight {
  border-color: #ff4d4d !important;
  outline: 1px solid #ff4d4d !important;
  background-color: rgba(255, 77, 77, 0.15) !important;
}
</style>

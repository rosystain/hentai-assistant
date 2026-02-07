<template>
  <div class="config-view">
    <h1>配置管理</h1>

    <div v-if="loading">加载中...</div>
    <div v-else-if="error" class="error-message">{{ error }}</div>
    <div v-else>
      <div>
        <!-- 配置标签导航 -->
        <div class="config-tabs">
          <button
            v-for="tab in configTabs"
            :key="tab.id"
            @click="switchConfigTab(tab.id)"
            :class="['tab-button', { active: activeConfigTab === tab.id }]"
          >
            {{ tab.label }}
          </button>
        </div>

        <!-- 配置表单 -->
        <form @submit.prevent="saveConfig">
          <Transition name="fade" mode="out-in">
            <div :key="activeConfigTab" class="tab-content">
              <div v-for="section in currentTabSections" :key="section.name" class="config-section">
                <h2>{{ getSectionLabel(section.name) }}</h2>
                <div>
                  <div v-for="field in section.orderedFields" :key="field.key" class="config-item" :class="{ 'config-item-inline': isBooleanField(section.name, field.key) }">
                    <div class="config-label-group">
                      <label :for="`${section.name}-${field.key}`">{{ getFieldLabel(section.name, field.key) }}</label>
                      <span v-if="getFieldDescription(section.name, field.key)" class="config-description">
                        {{ getFieldDescription(section.name, field.key) }}
                      </span>
                    </div>
                    <!-- 布尔型字段使用拨杆开关 -->
                    <label v-if="isBooleanField(section.name, field.key)" class="toggle-switch">
                      <input
                        type="checkbox"
                        :id="`${section.name}-${field.key}`"
                        :checked="isBooleanTrue(section.name, field.key)"
                        @change="toggleBoolean(section.name, field.key)"
                      />
                      <span class="toggle-slider"></span>
                    </label>
                    <!-- 非布尔型字段使用文本输入 -->
                    <input
                      v-else
                      :id="`${section.name}-${field.key}`"
                      v-model="(editableConfig[section.name] as ConfigItem)[field.key]"
                      type="text"
                    />
                    <!-- move_path 模板预览 -->
                    <div 
                      v-if="section.name === 'general' && field.key === 'move_path' && movePathPreview"
                      class="template-preview"
                    >
                      <span class="preview-label">预览：</span>
                      <code class="preview-value">{{ movePathPreview }}</code>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Transition>
          <button type="submit" :disabled="saving">保存配置</button>
          <div v-if="saving">保存中...</div>
          <div v-if="saveSuccess" class="success-message">配置保存成功！正在重新检查服务状态...</div>
          <div v-if="saveError" class="error-message">保存失败: {{ saveError }}</div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import { useTheme } from '@/composables/useTheme';
import { getFieldLabel, getFieldDescription, getSectionLabel, configLabels } from '@/config-labels';

interface ConfigItem {
  [key: string]: string;
}

interface OrderedConfigItem {
  key: string;
  value: string;
}

interface ConfigSection {
  [sectionName: string]: ConfigItem;
}

interface ConfigStatus {
  eh_valid: boolean;
  exh_valid: boolean;
  nh_toggle: boolean;
  aria2_toggle: boolean;
  komga_toggle: boolean;
  eh_funds?: {
    GP: number | string;
    Credits: number | string;
  };
}

interface FullConfig {
  [sectionName: string]: ConfigItem | ConfigStatus;
}

const config = ref<FullConfig>({});
const editableConfig = ref<FullConfig>({});
const loading = ref(true);
const error = ref<string | null>(null);
const saving = ref(false);
const saveSuccess = ref(false);
const saveError = ref<string | null>(null);
const { isDark } = useTheme();
const activeConfigTab = ref('basic');

const API_BASE_URL = '/api'; // 使用相对路径，通过 Vite 代理或 Flask 静态服务处理

// Jinja 模板预览的模拟数据
const sampleTemplateData: Record<string, string | null> = {
  filename: '[クジラックス] ろりとぼくらの。 [中国翻訳] [1234567].cbz',
  author: 'クジラックス',
  writer: 'クジラックス',
  penciller: 'クジラックス',
  series: 'ろりとぼくらの。',
  title: 'ろりとぼくらの。',
  translator: '某某汉化组',
  genre: 'Doujinshi',
  category: 'doujinshi',
  tags: 'lolicon, schoolgirl uniform',
  web: 'https://exhentai.org/g/1234567/abcdef/',
  agerating: 'Adults Only 18+',
  manga: 'YesAndRightToLeft',
  languageiso: 'zh',
  number: '1',
  originaltitle: 'ろりとぼくらの。'
};

// 简单的 Jinja-like 模板解析器
function renderJinjaPreview(template: string): string {
  if (!template) return '';
  
  let result = template;
  
  // 处理 {% if var %}...{% else %}...{% endif %} 条件语句
  const ifElseRegex = /\{%\s*if\s+(\w+)\s*%\}([\s\S]*?)\{%\s*else\s*%\}([\s\S]*?)\{%\s*endif\s*%\}/g;
  result = result.replace(ifElseRegex, (_match, varName, ifContent, elseContent) => {
    const value = sampleTemplateData[varName.toLowerCase()];
    return (value && value.trim()) ? ifContent : elseContent;
  });
  
  // 处理 {% if var %}...{% endif %} 条件语句（没有 else）
  const ifOnlyRegex = /\{%\s*if\s+(\w+)\s*%\}([\s\S]*?)\{%\s*endif\s*%\}/g;
  result = result.replace(ifOnlyRegex, (_match, varName, ifContent) => {
    const value = sampleTemplateData[varName.toLowerCase()];
    return (value && value.trim()) ? ifContent : '';
  });
  
  // 处理 {{variable}} 变量替换
  const varRegex = /\{\{\s*(\w+)\s*\}\}/g;
  result = result.replace(varRegex, (_match, varName) => {
    const value = sampleTemplateData[varName.toLowerCase()];
    return (value && value.trim()) ? value : 'Unknown';
  });
  
  return result;
}

// 计算 move_path 的预览值
const movePathPreview = computed(() => {
  const movePath = (editableConfig.value['general'] as ConfigItem)?.['move_path'];
  if (!movePath) return '';
  return renderJinjaPreview(movePath);
});

// 定义布尔类型的配置字段
const booleanFields: Record<string, string[]> = {
  general: ['keep_torrents', 'keep_original_file', 'prefer_japanese_title'],
  advanced: ['tags_translation', 'remove_ads', 'aggressive_series_detection', 'openai_series_detection', 'prefer_openai_series'],
  ehentai: ['favorite_sync', 'auto_download_favorites', 'hath_check_enabled'],
  aria2: ['enable'],
  komga: ['enable', 'index_sync']
};

// 判断字段是否为布尔类型
const isBooleanField = (section: string, key: string): boolean => {
  return booleanFields[section]?.includes(key) ?? false;
};

// 判断布尔字段当前值是否为 true
const isBooleanTrue = (section: string, key: string): boolean => {
  const value = (editableConfig.value[section] as ConfigItem)?.[key];
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    return ['true', 'yes', 'on', '1'].includes(value.toLowerCase());
  }
  return false;
};

// 切换布尔字段值
const toggleBoolean = (section: string, key: string) => {
  const sectionData = editableConfig.value[section] as ConfigItem;
  if (sectionData) {
    const currentValue = isBooleanTrue(section, key);
    sectionData[key] = currentValue ? 'false' : 'true';
  }
};

// 配置标签定义
const configTabs = [
  {
    id: 'basic',
    label: '基础配置',
    sections: ['general', 'advanced']
  },
  {
    id: 'sites',
    label: '站点配置',
    sections: ['ehentai', 'nhentai', 'hdoujin']
  },
  {
    id: 'integrations',
    label: '集成服务',
    sections: ['aria2', 'komga', 'openai']
  },
  {
    id: 'others',
    label: '其他配置',
    sections: ['comicinfo']
  }
];

const orderedConfigSections = computed(() => {
  return Object.entries(config.value)
    .filter(([name]) => name !== 'status' && name !== 'notification')
    .map(([name, data]) => {
      // 获取 configLabels 中该 section 的字段定义顺序
      const sectionLabels = configLabels[name];
      const labelOrder = sectionLabels ? Object.keys(sectionLabels) : [];
      
      // 按照 configLabels 中定义的顺序排序字段
      const sortedFields = Object.entries(data as ConfigItem)
        .map(([key, value]) => ({ key, value }))
        .sort((a, b) => {
          const indexA = labelOrder.indexOf(a.key);
          const indexB = labelOrder.indexOf(b.key);
          // 如果字段不在 labelOrder 中，放到最后
          const orderA = indexA === -1 ? Infinity : indexA;
          const orderB = indexB === -1 ? Infinity : indexB;
          return orderA - orderB;
        });
      
      return {
        name,
        data,
        orderedFields: sortedFields
      }
    })
});

// 当前标签的配置sections
const currentTabSections = computed(() => {
  const tab = configTabs.find(t => t.id === activeConfigTab.value);
  return orderedConfigSections.value.filter(section => 
    tab?.sections.includes(section.name)
  );
});

// 切换配置标签
const switchConfigTab = (tabId: string) => {
  activeConfigTab.value = tabId;
};

const fetchConfig = async () => {
  loading.value = true;
  error.value = null;
  try {
    const response = await axios.get(`${API_BASE_URL}/config`);
    config.value = response.data;
    // 深拷贝配置以便编辑
    editableConfig.value = JSON.parse(JSON.stringify(response.data));
  } catch (err) {
    error.value = '无法加载配置。请检查后端服务是否运行。';
    console.error(err);
  } finally {
    loading.value = false;
  }
};

const saveConfig = async () => {
  saving.value = true;
  saveSuccess.value = false;
  saveError.value = null;
  try {
    // 过滤掉 status 字段，因为后端不需要接收它
    const configToSave: FullConfig = {};
    for (const sectionName in editableConfig.value) {
      if (sectionName !== 'status') {
        configToSave[sectionName] = editableConfig.value[sectionName];
      }
    }
    await axios.post(`${API_BASE_URL}/config`, configToSave);
    saveSuccess.value = true;
    // 重新加载配置以获取最新的状态
    setTimeout(() => {
      location.reload();
    }, 1000); // 延迟1秒后刷新页面
  } catch (err) {
    saveError.value = '保存配置失败。';
    console.error(err);
  } finally {
    saving.value = false;
  }
};



onMounted(fetchConfig);
</script>

<style scoped>
.tabs {
  display: flex;
  margin-bottom: 20px;
  /* border-bottom: 1px solid #eee; */ /* Remove the faint line */
}

.tabs button {
  flex: 1; /* Distribute width equally */
  text-align: center;
  padding: 10px 20px;
  border: none;
  background-color: transparent;
  cursor: pointer;
  font-size: 16px;
  margin-right: 10px;
  border-bottom: 2px solid transparent;
  transition: all 0.3s ease;
  color: #555; /* Improved default text color for light mode */
}

.tabs button:last-child {
    margin-right: 0;
}

.tabs button.active {
  background-color: #007bff;
  color: white; /* 设置为反白颜色 */
  border-bottom-color: transparent; /* Hide the bottom border line for a cleaner look */
  font-weight: bold;
  border-radius: 5px; /* Apply border radius to all 4 corners */
}

/* 未激活的标签页在悬浮时只显示下划线 */
.tabs button:not(.active):hover {
    color: #007bff; /* Change text color to highlight color on hover */
    background-color: transparent; /* Ensure no background color appears */
    border-bottom-color: #007bff; /* Change underline to highlight color */
}

/* 配置标签导航 - 胶囊按钮式 */
.config-tabs {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-bottom: 24px;
}

.tab-button {
  padding: 10px 24px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #6c757d;
  cursor: pointer;
  transition: all 0.2s ease;
  font-size: 15px;
  font-weight: 500;
  margin: 0;
  width: auto;
  display: inline-block;
}

.tab-button:hover {
  color: #007bff;
  background: rgba(0, 123, 255, 0.08);
}

.tab-button.active {
  color: #fff;
  background: #007bff;
  font-weight: 600;
}

/* 标签内容动画 */
.tab-content {
  min-height: 200px;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(10px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-10px);
}

.config-view {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  text-align: center;
  margin-bottom: 20px;
}

h2 {
  color: #555;
  border-bottom: 2px solid #e9ecef;
  padding-bottom: 8px;
  margin-top: 0;
  margin-bottom: 20px;
  font-size: 18px;
  font-weight: 600;
}

.config-section {
  background: linear-gradient(135deg, #ffffff 0%, #f8f9fa 100%);
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 20px;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.07), 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
}

.config-section::before {
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

.config-section:hover::before {
  opacity: 1;
}

.config-item {
  display: flex;
  flex-direction: column;
  align-items: stretch; /* Make children full width */
  margin-bottom: 16px; /* Increased margin */
  gap: 6px; /* Space between label and input */
}

.config-item label {
  font-weight: 600;
  color: #555;
  font-size: 14px;
  text-align: left;
  word-wrap: break-word;
  hyphens: auto;
}

.config-label-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}

.config-label-group > label {
  margin-bottom: 0;
}

.config-description {
  font-size: 12px;
  color: #888;
  font-weight: normal;
  line-height: 1.4;
}


.config-item input[type="text"] {
  flex: 1;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 14px;
  line-height: 1.4;
  background-color: #ffffff;
  color: #333;
  transition: all 0.2s ease;
  min-height: 20px;
  box-sizing: border-box;
}

.config-item input[type="text"]:focus {
  border-color: #007bff;
  outline: none;
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
  background-color: #fefefe;
}

/* 模板预览区域样式 */
.template-preview {
  margin-top: 8px;
  padding: 10px 12px;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  border: 1px solid #dee2e6;
  border-radius: 6px;
  font-size: 13px;
  line-height: 1.5;
  word-break: break-all;
}

.template-preview .preview-label {
  color: #6c757d;
  font-weight: 500;
  margin-right: 6px;
}

.template-preview .preview-value {
  color: #28a745;
  background: rgba(40, 167, 69, 0.1);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 12px;
}

/* 布尔型配置项行内布局 */
.config-item-inline {
  flex-direction: row !important;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.config-item-inline label:first-child {
  margin-bottom: 0;
}

/* 拨杆开关样式 */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
  margin: 0;
  padding: 0;
}

.toggle-switch input {
  opacity: 0;
  width: 0;
  height: 0;
  position: absolute;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: #ccc;
  border-radius: 24px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-slider::before {
  position: absolute;
  content: "";
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background-color: white;
  border-radius: 50%;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.toggle-switch input:checked + .toggle-slider {
  background-color: #28a745;
}

.toggle-switch input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

.toggle-switch:hover .toggle-slider {
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
}


button {
  display: block;
  width: 150px;
  padding: 10px 15px;
  background-color: #007bff;
  color: white;
  border: none;
  border-radius: 5px;
  font-size: 16px;
  cursor: pointer;
  margin-top: 20px;
  margin-left: auto;
  margin-right: auto;
  transition: background-color 0.3s ease;
}

button:hover {
  background-color: #0056b3;
}

button:disabled {
  background-color: #cccccc;
  cursor: not-allowed;
}


.error-message {
  color: #dc3545;
  background-color: #f8d7da;
  border: 1px solid #f5c6cb;
  padding: 10px;
  border-radius: 5px;
  margin-bottom: 15px;
  text-align: center;
}

.success-message {
  color: #28a745;
  background-color: #d4edda;
  border: 1px solid #c3e6cb;
  padding: 10px;
  border-radius: 5px;
  margin-bottom: 15px;
  text-align: center;
}
</style>

<style scoped>
/* 移动端响应式设计 */
@media (max-width: 768px) {
  .config-view {
    padding: 15px;
  }

  h1 {
    font-size: 1.5em;
    margin-bottom: 20px;
  }

  h2 {
    font-size: 1.2em;
  }

  .config-section {
    padding: 12px;
  }

  /* The new layout is already mobile-friendly, so fewer overrides are needed */
  .config-item {
    gap: 8px;
    margin-bottom: 16px;
  }

  .config-item label {
    font-size: 13px;
  }

  .config-item input[type="text"] {
    width: 100%;
    padding: 12px;
    font-size: 16px; /* 防止移动端缩放 */
  }


  button {
    width: 100%;
    max-width: 200px;
  }

}

/* 深色模式适配 */
.dark .config-view {
  color: var(--text-color-light);
}

.dark h1, .dark h2 {
  color: var(--text-color-light);
}

.dark .config-section {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.05) 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3), 0 1px 3px rgba(0, 0, 0, 0.4);
}

.dark .config-section:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.08) 100%);
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
}

.dark .config-section::before {
  background: linear-gradient(90deg, #007bff 0%, #28a745 50%, #6f42c1 100%);
}

.dark .config-item label {
  color: var(--text-color-light);
}

.dark .config-description {
  color: rgba(255, 255, 255, 0.5);
}


.dark .config-item input[type="text"] {
  background-color: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.2);
  color: var(--text-color-light);
}

.dark .config-item input[type="text"]:focus {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
  background-color: rgba(255, 255, 255, 0.1);
}

/* 深色模式下的模板预览样式 */
.dark .template-preview {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.02) 100%);
  border-color: rgba(255, 255, 255, 0.15);
}

.dark .template-preview .preview-label {
  color: rgba(255, 255, 255, 0.6);
}

.dark .template-preview .preview-value {
  color: #4ade80;
  background: rgba(74, 222, 128, 0.15);
}

/* 深色模式下的拨杆开关样式 */
.dark .toggle-slider {
  background-color: #555;
}

.dark .toggle-switch input:checked + .toggle-slider {
  background-color: #28a745;
}

.dark .toggle-switch:hover .toggle-slider {
  box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.25);
}

.dark .error-message {
  background-color: rgba(220, 53, 69, 0.1);
  border-color: var(--danger-color);
  color: var(--danger-color);
}

.dark .success-message {
  background-color: rgba(40, 167, 69, 0.1);
  border-color: var(--success-color);
  color: var(--success-color);
}
</style>
<style scoped>
/* No longer needed as the border is removed */
/*
.dark .tabs {
  border-bottom-color: rgba(255, 255, 255, 0.12);
}
*/

/* 深色模式下的配置标签 */
.dark .tab-button {
  color: rgba(255, 255, 255, 0.6);
}

.dark .tab-button:hover {
  color: var(--primary-color);
  background: rgba(0, 123, 255, 0.15);
}

.dark .tab-button.active {
  color: #fff;
  background: var(--primary-color);
}

.dark .tabs button {
  color: var(--text-color-light);
}

.dark .tabs button.active {
  background-color: var(--primary-color);
  color: white; /* Ensure text is white in dark mode */
  border-bottom-color: transparent; /* Hide the bottom border line for a cleaner look */
}

.dark .tabs button:not(.active):hover {
  color: var(--primary-color); /* Change text color to highlight color on hover */
  background-color: transparent; /* Ensure no background color appears */
  border-bottom-color: var(--primary-color); /* Change underline to highlight color */
}
</style>

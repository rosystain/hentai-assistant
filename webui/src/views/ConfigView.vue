<template>
  <div class="config-view">
    <h1>配置管理</h1>
    <div v-if="loading">加载中...</div>
    <div v-else-if="error" class="error-message">{{ error }}</div>
    <div v-else>
      <form @submit.prevent="saveConfig">
        <div v-for="section in orderedConfigSections" :key="section.name" class="config-section">
          <h2 v-if="section.name !== 'status'">{{ section.name }}</h2>
          <div v-if="section.name !== 'status'">
            <div v-for="field in section.orderedFields" :key="field.key" class="config-item">
              <label :for="`${section.name}-${field.key}`">{{ field.key }}:</label>
              <input
                :id="`${section.name}-${field.key}`"
                v-model="(editableConfig[section.name] as ConfigItem)[field.key]"
                type="text"
              />
            </div>
          </div>
          <div v-else class="status-section">
            <h2>服务状态</h2>
            <p>E-Hentai: <span :class="statusClass((section.data as ConfigStatus).hath_toggle)">{{ statusText((section.data as ConfigStatus).hath_toggle) }}</span></p>
            <p>NHentai: <span :class="statusClass((section.data as ConfigStatus).nh_toggle)">{{ statusText((section.data as ConfigStatus).nh_toggle) }}</span></p>
            <p>Aria2: <span :class="statusClass((section.data as ConfigStatus).aria2_toggle)">{{ statusText((section.data as ConfigStatus).aria2_toggle) }}</span></p>
            <p>Komga: <span :class="statusClass((section.data as ConfigStatus).komga_toggle)">{{ statusText((section.data as ConfigStatus).komga_toggle) }}</span></p>
          </div>
        </div>
        <button type="submit" :disabled="saving">保存配置</button>
        <div v-if="saving">保存中...</div>
        <div v-if="saveSuccess" class="success-message">配置保存成功！正在重新检查服务状态...</div>
        <div v-if="saveError" class="error-message">保存失败: {{ saveError }}</div>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue';
import axios from 'axios';
import { useTheme } from '@/composables/useTheme';

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
  hath_toggle: boolean;
  nh_toggle: boolean;
  aria2_toggle: boolean;
  komga_toggle: boolean;
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

const API_BASE_URL = '/api'; // 使用相对路径，通过 Vite 代理或 Flask 静态服务处理

const orderedConfigSections = computed(() => {
  return Object.entries(config.value).map(([name, data]) => {
    const section: {
      name: string
      data: ConfigItem | ConfigStatus
      orderedFields?: OrderedConfigItem[]
    } = { name, data }

    if (name !== 'status') {
      section.orderedFields = Object.entries(data as ConfigItem).map(([key, value]) => ({
        key,
        value
      }))
    }

    return section
  })
});

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
    setTimeout(fetchConfig, 3000); // 等待后端检查配置完成
  } catch (err) {
    saveError.value = '保存配置失败。';
    console.error(err);
  } finally {
    saving.value = false;
  }
};

const statusClass = (status: boolean) => {
  return status ? 'status-success' : 'status-error';
};

const statusText = (status: boolean) => {
  return status ? '✅ 正常' : '❌ 异常';
};


onMounted(fetchConfig);
</script>

<style scoped>
.config-view {
  padding: 20px;
  max-width: 800px;
  margin: 0 auto;
  font-family: Arial, sans-serif;
}

h1 {
  color: #333;
  text-align: center;
  margin-bottom: 30px;
}

h2 {
  color: #555;
  border-bottom: 1px solid #eee;
  padding-bottom: 5px;
  margin-top: 20px;
  margin-bottom: 15px;
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
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.config-item label {
  flex: 0 0 160px;
  font-weight: 600;
  color: #555;
  font-size: 14px;
  line-height: 1.4;
  text-align: right;
  padding-right: 8px;
  word-wrap: break-word;
  hyphens: auto;
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

.status-section {
  margin-top: 20px;
  padding-top: 15px;
  border-top: 1px dashed #eee;
}

.status-section p {
  margin-bottom: 8px;
  font-size: 15px;
}

.status-success {
  color: #28a745; /* Green */
  font-weight: bold;
}

.status-error {
  color: #dc3545; /* Red */
  font-weight: bold;
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

  .config-item {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 16px;
  }

  .config-item label {
    flex: none;
    width: 100%;
    text-align: left;
    padding-right: 0;
    font-size: 13px;
    word-wrap: break-word;
    hyphens: auto;
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

  .status-section p {
    font-size: 14px;
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


.dark .status-section {
  border-top-color: var(--border-color);
}

.dark .status-section p {
  color: var(--text-color-light);
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

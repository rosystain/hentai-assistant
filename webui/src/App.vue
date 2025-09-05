<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'
import { useTheme } from '@/composables/useTheme'

const { isDark, userPreference, toggleTheme, setTheme } = useTheme()

const getThemeIcon = () => {
  if (userPreference.value === 'auto') {
    return '🌓'
  } else if (userPreference.value === 'light') {
    return '☀️'
  } else {
    return '🌙'
  }
}

const cycleTheme = () => {
  if (userPreference.value === 'auto') {
    setTheme('light')
  } else if (userPreference.value === 'light') {
    setTheme('dark')
  } else {
    setTheme('auto')
  }
}
</script>

<template>
  <header class="app-header">
    <nav class="main-nav">
      <RouterLink to="/" class="nav-link">首页</RouterLink>
      <RouterLink to="/config" class="nav-link">配置</RouterLink>
      <RouterLink to="/download" class="nav-link">下载</RouterLink>
      <RouterLink to="/tasks" class="nav-link">任务</RouterLink>
      <button @click="cycleTheme" class="theme-toggle" :title="`当前模式: ${userPreference === 'auto' ? '自动' : userPreference === 'light' ? '浅色' : '暗色'} (点击切换)`">
        {{ getThemeIcon() }}
      </button>
    </nav>
  </header>

  <main class="app-main">
    <RouterView />
  </main>
</template>

<style scoped>
.app-header {
  background-color: var(--light-color);
  padding: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 1000;
  transition: background-color 0.3s ease;
}

.dark .app-header {
  background-color: var(--dark-color);
}

.main-nav {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 15px;
  flex-wrap: wrap;
}

.nav-link {
  color: var(--text-color-dark);
  text-decoration: none;
  font-size: 1.1rem;
  padding: 0.5rem 1rem;
  border-radius: var(--border-radius);
  transition: all 0.3s ease;
}

.dark .nav-link {
  color: var(--white-color);
}

.nav-link:hover {
  background-color: rgba(0, 0, 0, 0.05);
}

.dark .nav-link:hover {
  background-color: rgba(255, 255, 255, 0.1);
}

.nav-link.router-link-exact-active {
  background-color: var(--primary-color);
  color: var(--white-color);
  font-weight: bold;
}

.theme-toggle {
  background: none;
  border: 1px solid var(--border-color);
  color: var(--text-color-dark);
  padding: 0.5rem;
  border-radius: 50%;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
  font-size: 1.2rem;
}

.dark .theme-toggle {
  border-color: rgba(255, 255, 255, 0.3);
  color: var(--white-color);
}

.theme-toggle:hover {
  background-color: rgba(0, 0, 0, 0.05);
  border-color: var(--primary-color);
}

.dark .theme-toggle:hover {
  background-color: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.5);
}

.app-main {
  min-height: 100vh;
  background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
}

.dark .app-main {
  background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
}

/* 移动端响应式设计 */
@media (max-width: 768px) {
  .app-header {
    padding: 0.8rem;
  }

  .main-nav {
    gap: 10px;
  }

  .nav-link {
    font-size: 1rem;
    padding: 0.4rem 0.8rem;
  }

  .theme-toggle {
    width: 36px;
    height: 36px;
    font-size: 1.1rem;
  }

  .app-main {
    padding: 15px;
  }
}

@media (max-width: 480px) {
  .main-nav {
    gap: 8px;
  }

  .nav-link {
    font-size: 0.9rem;
    padding: 0.3rem 0.6rem;
  }

  .theme-toggle {
    width: 32px;
    height: 32px;
    font-size: 1rem;
  }
}
</style>

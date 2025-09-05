<script setup lang="ts">
import { RouterLink } from 'vue-router'
import IconDownload from '../components/icons/IconDownload.vue'
import IconTaskList from '../components/icons/IconTaskList.vue'
import IconConfig from '../components/icons/IconConfig.vue'
import { useTaskStats } from '../composables/useTaskStats'

const { stats, loading } = useTaskStats()
</script>

<template>
  <main class="home-view">
    <div class="hero-section">
      <h1>欢迎使用 hentai-assistant Web UI</h1>
      <p class="subtitle">一站式管理您的本子下载任务和配置</p>
    </div>

    <div class="features-grid">
      <RouterLink to="/download" class="feature-card">
        <div class="card-icon">
          <IconDownload />
        </div>
        <h3>添加下载</h3>
        <p>通过 URL 添加下载任务</p>
        <div class="card-arrow">→</div>
      </RouterLink>

      <RouterLink to="/tasks" class="feature-card">
        <div class="card-icon">
          <IconTaskList />
        </div>
        <h3>任务列表</h3>
        <p>查看当前和历史任务状态</p>
        <div class="card-arrow">→</div>
      </RouterLink>

      <RouterLink to="/config" class="feature-card">
        <div class="card-icon">
          <IconConfig />
        </div>
        <h3>系统配置</h3>
        <p>设置应用程序参数和选项</p>
        <div class="card-arrow">→</div>
      </RouterLink>
    </div>

    <div class="stats-section">
      <div class="stat-item">
        <div class="stat-number" :class="{ loading: loading && !stats }">
          {{ stats?.total ?? '-' }}
        </div>
        <div class="stat-label">总任务数</div>
      </div>
      <div class="stat-item">
        <div class="stat-number" :class="{ loading: loading && !stats }">
          {{ stats?.in_progress ?? '-' }}
        </div>
        <div class="stat-label">进行中</div>
      </div>
      <div class="stat-item">
        <div class="stat-number" :class="{ loading: loading && !stats }">
          {{ stats?.completed ?? '-' }}
        </div>
        <div class="stat-label">已完成</div>
      </div>
      <div class="stat-item">
        <div class="stat-number" :class="{ loading: loading && !stats }">
          {{ stats?.failed ?? '-' }}
        </div>
        <div class="stat-label">失败任务</div>
      </div>
    </div>
  </main>
</template>

<style scoped>
.home-view {
  min-height: 100vh;
}

.hero-section {
  text-align: center;
  margin-bottom: 60px;
}

.hero-section h1 {
  font-size: 2.5rem;
  color: var(--dark-color);
  margin-bottom: 16px;
  font-weight: 700;
}

.subtitle {
  font-size: 1.2rem;
  color: var(--secondary-color);
  margin-bottom: 0;
}

.features-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 24px;
  max-width: 1000px;
  margin: 0 auto 60px;
}

.feature-card {
  display: flex;
  flex-direction: column;
  padding: 32px 24px;
  background: var(--white-color);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  text-decoration: none;
  color: inherit;
  transition: all 0.3s ease;
  position: relative;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.feature-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, var(--primary-color), var(--info-color));
}

.feature-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.15);
}

.feature-card:hover .card-arrow {
  transform: translateX(4px);
}

.card-icon {
  margin-bottom: 20px;
  display: flex;
  justify-content: center;
  align-items: center;
  height: 80px;
}

.card-icon svg {
  width: 48px;
  height: 48px;
  color: var(--primary-color);
}

.feature-card h3 {
  font-size: 1.5rem;
  color: var(--dark-color);
  margin-bottom: 12px;
  font-weight: 600;
}

.feature-card p {
  color: var(--secondary-color);
  margin-bottom: 24px;
  line-height: 1.5;
  flex-grow: 1;
}

.card-arrow {
  font-size: 1.5rem;
  color: var(--primary-color);
  transition: transform 0.3s ease;
  align-self: flex-end;
}

.stats-section {
  display: flex;
  justify-content: center;
  gap: 48px;
  flex-wrap: wrap;
}

.stat-item {
  text-align: center;
  padding: 20px;
}

.stat-number {
  font-size: 2.5rem;
  font-weight: 700;
  color: var(--primary-color);
  margin-bottom: 8px;
  min-height: 3rem;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-number.loading {
  color: var(--secondary-color);
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.stat-label {
  font-size: 1rem;
  color: var(--secondary-color);
  font-weight: 500;
}


.dark .hero-section h1 {
  color: var(--text-color-light);
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}

.dark .subtitle {
  color: rgba(255, 255, 255, 0.7);
}

.dark .feature-card {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.05) 100%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  backdrop-filter: blur(10px);
}

.dark .feature-card:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.08) 100%);
  border-color: rgba(255, 255, 255, 0.2);
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.3);
}

.dark .feature-card h3 {
  color: var(--text-color-light);
}

.dark .feature-card p {
  color: rgba(255, 255, 255, 0.7);
}

.dark .card-icon svg {
  color: var(--primary-color);
  filter: drop-shadow(0 2px 4px rgba(0, 123, 255, 0.3));
}

.dark .card-arrow {
  color: var(--primary-color);
}

.dark .stat-number {
  color: var(--primary-color);
  text-shadow: 0 2px 4px rgba(0, 123, 255, 0.3);
}

.dark .stat-label {
  color: rgba(255, 255, 255, 0.7);
}

.dark .stat-number.loading {
  color: rgba(255, 255, 255, 0.5);
}

/* 响应式设计 - 移动端优化 */
@media (max-width: 768px) {
  .home-view {
    min-height: 100vh;
  }

  .hero-section {
    margin-bottom: 40px;
  }

  .hero-section h1 {
    font-size: 1.8rem;
    line-height: 1.3;
    margin-bottom: 12px;
  }

  .subtitle {
    font-size: 1rem;
  }

  .features-grid {
    grid-template-columns: 1fr;
    gap: 16px;
    margin-bottom: 40px;
  }

  .feature-card {
    padding: 24px 20px;
    border-radius: 12px;
  }

  .card-icon {
    height: 60px;
    margin-bottom: 16px;
  }

  .card-icon svg {
    width: 40px;
    height: 40px;
  }

  .feature-card h3 {
    font-size: 1.3rem;
    margin-bottom: 8px;
  }

  .feature-card p {
    font-size: 0.95rem;
    margin-bottom: 20px;
  }

  .stats-section {
    gap: 16px;
    flex-wrap: wrap;
    justify-content: center;
  }

  .stat-item {
    padding: 12px;
    min-width: 120px;
    flex: 1;
  }

  .stat-number {
    font-size: 1.8rem;
    min-height: 2.5rem;
  }

  .stat-label {
    font-size: 0.9rem;
  }
}

/* 超小屏幕优化 */
@media (max-width: 480px) {
  .home-view {
    /* 背景已完全填充，无需额外padding */
  }

  .hero-section h1 {
    font-size: 1.5rem;
  }

  .subtitle {
    font-size: 0.9rem;
  }

  .feature-card {
    padding: 20px 16px;
  }

  .card-icon {
    height: 50px;
    margin-bottom: 12px;
  }

  .card-icon svg {
    width: 36px;
    height: 36px;
  }

  .feature-card h3 {
    font-size: 1.2rem;
  }

  .feature-card p {
    font-size: 0.9rem;
  }

  .stat-item {
    min-width: 100px;
    padding: 10px;
  }

  .stat-number {
    font-size: 1.6rem;
  }

  .stat-label {
    font-size: 0.85rem;
  }
}

/* 触摸设备优化 */
@media (hover: none) and (pointer: coarse) {
  .feature-card:hover {
    transform: none;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  }

  .feature-card:active {
    transform: scale(0.98);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.1);
  }
}

/* 减少动画对性能敏感用户的影响 */
@media (prefers-reduced-motion: reduce) {
  .feature-card,
  .card-arrow,
  .stat-number {
    transition: none;
    animation: none;
  }
}
</style>

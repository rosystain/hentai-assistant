import { ref, onMounted, onUnmounted } from 'vue'
import axios from 'axios'

export interface TaskStats {
  total: number
  in_progress: number
  completed: number
  failed: number
  status_counts: Record<string, number>
}

export function useTaskStats() {
  const stats = ref<TaskStats | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const refreshInterval = ref<number | null>(null)

  const fetchStats = async () => {
    loading.value = true
    error.value = null
    try {
      const response = await axios.get('/api/task_stats')
      stats.value = response.data
    } catch (err) {
      error.value = '获取任务统计信息失败'
      console.error('Failed to fetch task stats:', err)
    } finally {
      loading.value = false
    }
  }

  const startAutoRefresh = () => {
    stopAutoRefresh()
    refreshInterval.value = window.setInterval(fetchStats, 30000)
  }

  const stopAutoRefresh = () => {
    if (refreshInterval.value !== null) {
      clearInterval(refreshInterval.value)
      refreshInterval.value = null
    }
  }

  onMounted(() => {
    fetchStats()
    startAutoRefresh()
  })

  onUnmounted(() => {
    stopAutoRefresh()
  })

  return {
    stats,
    loading,
    error,
    fetchStats,
    startAutoRefresh,
    stopAutoRefresh
  }
}

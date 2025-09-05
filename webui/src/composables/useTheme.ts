import { ref, onMounted, watch } from 'vue'

export function useTheme() {
  const isDark = ref(false)
  const userPreference = ref<'auto' | 'light' | 'dark'>('auto')

  const applyTheme = (dark: boolean) => {
    if (dark) {
      document.documentElement.classList.add('dark')
      document.documentElement.classList.remove('light')
    } else {
      document.documentElement.classList.add('light')
      document.documentElement.classList.remove('dark')
    }
  }

  const checkSystemDarkMode = () => {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  }

  const updateTheme = () => {
    if (userPreference.value === 'auto') {
      isDark.value = checkSystemDarkMode()
    } else {
      isDark.value = userPreference.value === 'dark'
    }
    applyTheme(isDark.value)
  }

  const toggleTheme = () => {
    if (userPreference.value === 'auto') {
      userPreference.value = isDark.value ? 'light' : 'dark'
    } else if (userPreference.value === 'light') {
      userPreference.value = 'dark'
    } else {
      userPreference.value = 'light'
    }
    localStorage.setItem('theme-preference', userPreference.value)
    updateTheme()
  }

  const setTheme = (theme: 'auto' | 'light' | 'dark') => {
    userPreference.value = theme
    localStorage.setItem('theme-preference', theme)
    updateTheme()
  }

  onMounted(() => {
    // 从 localStorage 读取用户偏好
    const savedPreference = localStorage.getItem('theme-preference') as 'auto' | 'light' | 'dark' | null
    if (savedPreference) {
      userPreference.value = savedPreference
    }

    updateTheme()

    // 监听系统主题变化
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
      if (userPreference.value === 'auto') {
        updateTheme()
      }
    })
  })

  watch(isDark, (newValue) => {
    applyTheme(newValue)
  })

  return {
    isDark,
    userPreference,
    toggleTheme,
    setTheme
  }
}

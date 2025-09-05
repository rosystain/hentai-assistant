import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import ConfigView from '../views/ConfigView.vue' // 导入 ConfigView
import DownloadView from '../views/DownloadView.vue' // 导入 DownloadView
import TaskListView from '../views/TaskListView.vue' // 导入 TaskListView

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/config', // 添加新的配置路由
      name: 'config',
      component: ConfigView,
    },
    {
      path: '/download', // 添加新的下载任务路由
      name: 'download',
      component: DownloadView,
    },
    {
      path: '/tasks', // 添加新的任务列表路由
      name: 'tasks',
      component: TaskListView,
    },
  ],
})

export default router

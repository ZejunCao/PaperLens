import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'library',
      component: () => import('@/views/LibraryView.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
    },
    {
      path: '/papers/:id',
      name: 'reader',
      component: () => import('@/views/ReaderView.vue'),
      props: true,
    },
  ],
})

export default router

import { createApp } from 'vue'
import PanelApp from './PanelApp.vue'
import './panel.css'

createApp(PanelApp, { page: document.getElementById('app')!.dataset.page! }).mount('#app')

import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import VueKonva from 'vue-konva'
import 'element-plus/dist/index.css'

import App from './App.vue'
import { createAppRouter } from './router'
import './styles/base.css'

createApp(App).use(ElementPlus).use(VueKonva).use(createAppRouter()).mount('#app')

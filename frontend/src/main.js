import { createApp } from 'vue';
import App from './App.vue';
import router from './router';
import { handleOAuthCallback } from './utils/auth';

// 登录回调会跳到根路径 /?token=... ，因此在启动阶段统一处理 token，
// 确保写入 localStorage 后再发业务请求。
handleOAuthCallback();

const app = createApp(App);
app.use(router);
app.mount('#app');

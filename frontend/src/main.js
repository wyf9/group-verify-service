import { createApp } from 'vue';
import ArcoVue from '@arco-design/web-vue';
import '@arco-design/web-vue/dist/arco.css';
import App from './App.vue';

const app = createApp(App);
app.use(ArcoVue);

if (typeof window !== 'undefined' && window.matchMedia) {
  const mql = window.matchMedia('(prefers-color-scheme: dark)');
  const applyTheme = (isDark) => {
    if (isDark) document.body.setAttribute('arco-theme', 'dark');
    else document.body.removeAttribute('arco-theme');
  };
  applyTheme(mql.matches);
  const onChange = (e) => applyTheme(e.matches);
  if (mql.addEventListener) mql.addEventListener('change', onChange);
  else if (mql.addListener) mql.addListener(onChange);
}

app.mount('#app');

<template>
  <a-config-provider :locale="arcoLocale">
    <div class="page">
      <template v-if="adminMode">
        <div v-if="adminRoute === 'login'" class="login-wrap">
          <AdminLoginView :on-login-success="goAdminHome" />
        </div>
        <AdminView v-else :on-logout="goAdminLogin" />
      </template>
      <VerifyView v-else :t="t" />
    </div>
  </a-config-provider>
</template>

<script setup>
import { computed, defineAsyncComponent, onMounted, ref, watch } from 'vue';
import VerifyView from './view/Verify/index.vue';
import { isAdminMode } from './utils/url';

// 管理后台仅在访问 /admin 时才需要，异步加载以拆分成独立 chunk，
// 避免公开的入群验证页也加载后台代码。
const AdminLoginView = defineAsyncComponent(() => import('./view/Admin/Login/index.vue'));
const AdminView = defineAsyncComponent(() => import('./view/Admin/index.vue'));
import { createTranslator, getArcoLocale, getInitialLocale, setLocale } from './i18n';

const locale = ref(setLocale(getInitialLocale()));
const arcoLocale = computed(() => getArcoLocale(locale.value));
const t = createTranslator(() => locale.value);

function updateLocale(nextLocale) {
  locale.value = setLocale(nextLocale);
  return locale.value;
}

const adminMode = ref(false);
const currentPath = ref('');

function readPath() {
  currentPath.value = window.location.pathname || '';
}

function navigateTo(path) {
  const next = String(path || '/');
  if ((window.location.pathname || '') === next) return;
  window.history.pushState({}, '', next);
  readPath();
}

const adminRoute = computed(() => {
  const p = currentPath.value || '';
  if (p === '/admin/login' || p === '/admin/login/') return 'login';
  return 'home';
});

function goAdminLogin() {
  navigateTo('/admin/login');
}

function goAdminHome() {
  navigateTo('/admin');
}

watch(
  [adminMode, adminRoute],
  () => {
    if (typeof document === 'undefined') return;
    if (!adminMode.value) {
      document.title = '入群验证';
    } else {
      document.title = adminRoute.value === 'login' ? '管理后台登录' : '管理后台';
    }
  },
  { immediate: true }
);

onMounted(() => {
  adminMode.value = isAdminMode();
  readPath();
  window.addEventListener('popstate', readPath);
});
</script>

<style scoped>
.page {
  width: 100%;
  min-height: 100vh;
  margin: 0;
  padding: 0;
}

.login-wrap {
  width: 100%;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  box-sizing: border-box;
}
</style>

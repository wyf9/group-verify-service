<template>
  <a-space direction="vertical" size="medium" fill>
    <a-alert type="info" :show-icon="true">
      记录每次验证行为。悬停「关联 Key」查看备注，悬停「浏览器」查看完整 User-Agent。
    </a-alert>

    <a-space align="center" justify="space-between" fill>
      <a-space wrap>
        <a-button :loading="submitting" @click="onRefresh">刷新</a-button>
        <a-input
          v-model="filterGroupId"
          placeholder="按群号过滤"
          allow-clear
          style="width: 160px"
          @press-enter="onSearch"
        />
        <a-select v-model="filterResult" style="width: 140px" @change="onSearch">
          <a-option value="">全部结果</a-option>
          <a-option value="1">验证通过</a-option>
          <a-option value="0">验证失败</a-option>
        </a-select>
        <a-input
          v-model="filterKeyId"
          placeholder="按 Key ID 过滤"
          allow-clear
          style="width: 160px"
          @press-enter="onSearch"
        />
        <a-button type="primary" :loading="submitting" @click="onSearch">查询</a-button>
      </a-space>
      <a-typography-text type="secondary">共 {{ total }} 条</a-typography-text>
    </a-space>

    <a-result v-if="errorText" status="error" title="加载失败" :subtitle="errorText" />

    <template v-else>
      <a-table
        :columns="columns"
        :data="items"
        :loading="submitting"
        :pagination="false"
        row-key="id"
        size="medium"
      >
        <template #createdAt="{ record }">
          <span>{{ formatTime(record && record.created_at) }}</span>
        </template>
        <template #relKey="{ record }">
          <a-tooltip v-if="record && record.api_key_id" :content="keyTooltip(record)">
            <a-tag color="arcoblue">{{ record.api_key_masked || ('Key#' + record.api_key_id) }}</a-tag>
          </a-tooltip>
          <a-typography-text v-else type="secondary">-</a-typography-text>
        </template>
        <template #ip="{ record }">
          <span>{{ (record && record.ip) || '-' }}</span>
        </template>
        <template #ua="{ record }">
          <a-tooltip v-if="record && record.user_agent" :content="record.user_agent">
            <a-tag>{{ parseBrowser(record.user_agent) }}</a-tag>
          </a-tooltip>
          <a-typography-text v-else type="secondary">-</a-typography-text>
        </template>
        <template #result="{ record }">
          <a-tag :color="record && record.result ? 'green' : 'red'">
            {{ record && record.result ? '通过' : '失败' }}
          </a-tag>
        </template>
        <template #code="{ record }">
          <a-typography-text v-if="record && record.code" code>{{ record.code }}</a-typography-text>
          <a-typography-text v-else type="secondary">-</a-typography-text>
        </template>
      </a-table>

      <a-space align="center" justify="space-between" fill>
        <a-typography-text type="secondary">第 {{ page }} 页</a-typography-text>
        <a-space>
          <a-button size="small" :disabled="page <= 1 || submitting" @click="onPrev">上一页</a-button>
          <a-button size="small" :disabled="!hasNext || submitting" @click="onNext">下一页</a-button>
        </a-space>
      </a-space>
    </template>
  </a-space>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { Message } from '@arco-design/web-vue';
import { listVerifyLogs } from '../../../api/adminSettings';
import { parseBrowser } from '../../../utils/ua';

const props = defineProps({
  token: { type: String, default: '' },
  onUnauthorized: { type: Function, default: null }
});

const tokenRef = computed(() => String(props.token || ''));

const submitting = ref(false);
const errorText = ref('');
const items = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(20);

const filterGroupId = ref('');
const filterResult = ref('');
const filterKeyId = ref('');

const hasNext = computed(() => page.value * pageSize.value < total.value);

const columns = [
  { title: '时间', width: 180, slotName: 'createdAt' },
  { title: '关联 Key', width: 140, slotName: 'relKey' },
  { title: '群号', dataIndex: 'group_id', width: 120 },
  { title: '用户', dataIndex: 'user_id', width: 120 },
  { title: 'IP', width: 140, slotName: 'ip' },
  { title: '浏览器', width: 120, slotName: 'ua' },
  { title: '结果', width: 90, slotName: 'result' },
  { title: '验证码', width: 110, slotName: 'code' }
];

function keyTooltip(record) {
  const note = record && record.api_key_note ? String(record.api_key_note) : '';
  return note ? `备注：${note}` : '（无备注）';
}

function formatTime(ts) {
  const n = Number(ts || 0);
  if (!n) return '-';
  try {
    return new Date(n * 1000).toLocaleString('zh-CN', { hour12: false });
  } catch (e) {
    return String(n);
  }
}

function buildParams() {
  const params = { page: page.value, page_size: pageSize.value };
  const gid = String(filterGroupId.value || '').trim();
  if (gid) params.group_id = gid;
  const r = String(filterResult.value || '');
  if (r === '0' || r === '1') params.result = r;
  const kid = Number(String(filterKeyId.value || '').trim());
  if (Number.isFinite(kid) && kid > 0) params.api_key_id = Math.floor(kid);
  return params;
}

async function loadItems() {
  errorText.value = '';
  submitting.value = true;
  try {
    const token = tokenRef.value ? String(tokenRef.value) : '';
    if (!token) {
      if (props.onUnauthorized) props.onUnauthorized();
      errorText.value = '登录已过期，请重新登录';
      return false;
    }
    const { data } = await listVerifyLogs(token, buildParams());
    if (data && data.code === 0 && data.data && Array.isArray(data.data.items)) {
      items.value = data.data.items;
      total.value = Number(data.data.total || 0);
      return true;
    }
    if (data && data.code === 401) {
      if (props.onUnauthorized) props.onUnauthorized();
      errorText.value = '登录已过期，请重新登录';
      return false;
    }
    errorText.value = (data && data.msg) || '加载失败';
    return false;
  } catch (e) {
    errorText.value = '网络异常，请稍后重试';
    Message.error(errorText.value);
    return false;
  } finally {
    submitting.value = false;
  }
}

async function onSearch() {
  page.value = 1;
  await loadItems();
}

async function onRefresh() {
  await loadItems();
}

async function onPrev() {
  if (page.value <= 1) return;
  page.value -= 1;
  await loadItems();
}

async function onNext() {
  if (!hasNext.value) return;
  page.value += 1;
  await loadItems();
}

watch(
  () => tokenRef.value,
  (t) => {
    if (t) loadItems();
    else items.value = [];
  }
);

onMounted(() => {
  if (!tokenRef.value) return;
  loadItems();
});
</script>

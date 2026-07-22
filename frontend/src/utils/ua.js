// 从 User-Agent 字符串中模糊匹配出浏览器类型（仅用于展示）
// 注意：需要在通用 Chrome 之前匹配这些「套壳/内嵌」浏览器，
// 因为它们的 UA 里通常也包含 Chrome 字段（如 QQ、微信）。
const UA_RULES = [
  { name: 'MicroMessenger', label: '微信' },
  { name: 'QQBrowser', label: 'QQ浏览器' },
  { name: 'MQQBrowser', label: 'QQ浏览器' },
  { name: 'QQ', label: 'QQ' },
  { name: 'UCBrowser', label: 'UC' },
  { name: 'Quark', label: '夸克' },
  { name: 'Edg', label: 'Edge' },
  { name: 'Edge', label: 'Edge' },
  { name: 'OPR', label: 'Opera' },
  { name: 'Opera', label: 'Opera' },
  { name: 'SamsungBrowser', label: 'Samsung' },
  { name: 'Firefox', label: 'Firefox' },
  { name: 'Chrome', label: 'Chrome' },
  { name: 'CriOS', label: 'Chrome' },
  { name: 'Safari', label: 'Safari' }
];

export function parseBrowser(ua) {
  const s = String(ua || '');
  if (!s) return '-';
  for (const rule of UA_RULES) {
    const re = new RegExp('\\b' + rule.name + '[\\/ ]', 'i');
    if (re.test(s) || s.toLowerCase().includes(rule.name.toLowerCase())) {
      return rule.label;
    }
  }
  return '未知';
}

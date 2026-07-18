<?php
namespace app\traits;

use think\facade\Db;

/**
 * 共享的 API Key 与 Settings 操作方法
 * 消除 AdminApiKeysController、AdminSettingsController、ApiAuth 之间的代码重复
 */
trait ApiKeyTrait
{
    protected static bool $traitSettingsReady = false;
    protected static bool $traitApiKeysReady = false;
    protected static ?int $traitCachedDefaultId = null;
    protected static int $traitCachedDefaultIdAt = 0;

    protected function ensureSettingsReady(): void
    {
        if (self::$traitSettingsReady) {
            return;
        }
        ensure_settings_table();
        self::$traitSettingsReady = true;
    }

    protected function ensureApiKeysReady(): void
    {
        if (self::$traitApiKeysReady) {
            return;
        }
        ensure_api_keys_table();
        self::$traitApiKeysReady = true;
    }

    protected function getDefaultApiKeyId(): int
    {
        $this->ensureApiKeysReady();
        $now = time();
        if (self::$traitCachedDefaultId !== null && ($now - self::$traitCachedDefaultIdAt) <= 3) {
            return (int)self::$traitCachedDefaultId;
        }
        $id = 0;
        try {
            $v = Db::name('api_keys')->order('id', 'asc')->value('id');
            $id = $v !== null ? (int)$v : 0;
        } catch (\Throwable $e) {
            $id = 0;
        }
        self::$traitCachedDefaultId = $id;
        self::$traitCachedDefaultIdAt = $now;
        return $id;
    }

    /**
     * 探测 settings 表使用的字段名（name 或 key），复用 common.php 中的 detect_settings_field()
     */
    protected function detectSettingsField(): string
    {
        return detect_settings_field();
    }

    protected function getSettingRaw(string $key): ?string
    {
        $this->ensureSettingsReady();
        $field = $this->detectSettingsField();

        try {
            $value = Db::name('settings')->where($field, $key)->value('value');
            return $value !== null ? (string)$value : null;
        } catch (\Throwable $e) {
            return null;
        }
    }

    protected function upsertSetting(string $key, string $value): void
    {
        $this->ensureSettingsReady();
        $field = $this->detectSettingsField();
        $ts = time();

        try {
            $updated = (int)Db::name('settings')->where($field, $key)->update([
                'value' => $value,
                'updated_at' => $ts,
            ]);

            if ($updated > 0) {
                return;
            }

            Db::name('settings')->insert([
                $field => $key,
                'value' => $value,
                'created_at' => $ts,
                'updated_at' => $ts,
            ]);
        } catch (\Throwable $e) {
        }
    }

    protected function deleteSetting(string $key): void
    {
        $this->ensureSettingsReady();
        $field = $this->detectSettingsField();

        try {
            Db::name('settings')->where($field, $key)->delete();
        } catch (\Throwable $e) {
        }
    }

    protected function parseApiKeys(string $raw): array
    {
        $v = trim($raw);
        if ($v === '') {
            return [];
        }

        if (str_starts_with($v, '[') && str_ends_with($v, ']')) {
            $decoded = json_decode($v, true);
            if (is_array($decoded)) {
                $keys = [];
                foreach ($decoded as $it) {
                    if (!is_string($it)) {
                        continue;
                    }
                    $k = trim($it);
                    if ($k === '') {
                        continue;
                    }
                    $keys[$k] = true;
                }
                return array_keys($keys);
            }
        }

        $parts = preg_split('/[,\s;，；]+/u', $v) ?: [];
        $keys = [];
        foreach ($parts as $p) {
            $k = trim((string)$p);
            if ($k === '') {
                continue;
            }
            $keys[$k] = true;
        }
        return array_keys($keys);
    }

    protected function maskSecret(string $value): string
    {
        $v = trim($value);
        if ($v === '') {
            return '';
        }
        if (mb_strlen($v) <= 8) {
            return '******';
        }
        return mb_substr($v, 0, 4) . '...' . mb_substr($v, -4);
    }

    protected function getJsonBody(): array
    {
        $raw = (string)$this->request->getInput();
        if ($raw === '') {
            return [];
        }
        $data = json_decode($raw, true);
        return is_array($data) ? $data : [];
    }

    protected function ensureApiKeysMigrated(): void
    {
        $this->ensureApiKeysReady();
        try {
            $any = Db::name('api_keys')->where('id', '>', 0)->limit(1)->value('id');
            if ($any !== null) {
                return;
            }
        } catch (\Throwable $e) {
        }

        $raw = $this->getSettingRaw('API_KEY');
        if ($raw === null || trim((string)$raw) === '') {
            $envValue = env('API_KEY', null);
            $raw = $envValue !== null ? (string)$envValue : '';
        }

        $keys = $this->parseApiKeys((string)$raw);
        if (!$keys) {
            return;
        }

        $ts = time();
        foreach ($keys as $k) {
            try {
                Db::name('api_keys')->insert([
                    'hash' => hash('sha256', $k),
                    'created_at' => $ts,
                    'updated_at' => $ts,
                ]);
            } catch (\Throwable $e) {
            }
        }

        $this->deleteSetting('API_KEY');
    }
}

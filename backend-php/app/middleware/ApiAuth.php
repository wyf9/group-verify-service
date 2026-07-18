<?php
namespace app\middleware;

use app\traits\ApiKeyTrait;
use think\facade\Db;

class ApiAuth
{
    use ApiKeyTrait;

    protected static ?array $cachedApiKeyRows = null;
    protected static int $cachedApiKeyRowsAt = 0;

    public static function clearCache(): void
    {
        self::$cachedApiKeyRows = null;
        self::$cachedApiKeyRowsAt = 0;
    }

    protected function readApiKeyRowsFromTable(): array
    {
        $this->ensureApiKeysReady();
        try {
            $rows = Db::name('api_keys')->field('id,hash')->select()->toArray();
            $items = [];
            foreach ($rows ?: [] as $r) {
                $id = (int)($r['id'] ?? 0);
                $h = trim((string)($r['hash'] ?? ''));
                if ($id <= 0 || $h === '') {
                    continue;
                }
                $items[] = ['id' => $id, 'hash' => $h];
            }
            return $items;
        } catch (\Throwable $e) {
            return [];
        }
    }

    protected function writeApiKeysToTable(array $keys): void
    {
        $this->ensureApiKeysReady();
        $ts = time();
        foreach ($keys as $v) {
            $k = trim((string)$v);
            if ($k === '') {
                continue;
            }
            try {
                Db::name('api_keys')->insert([
                    'hash' => hash('sha256', $k),
                    'created_at' => $ts,
                    'updated_at' => $ts,
                ]);
            } catch (\Throwable $e) {
            }
        }
    }

    protected function getApiKeyRows(): array
    {
        $now = time();
        if (self::$cachedApiKeyRows !== null && ($now - self::$cachedApiKeyRowsAt) <= 3) {
            return self::$cachedApiKeyRows;
        }

        $fromTable = $this->readApiKeyRowsFromTable();
        if ($fromTable) {
            self::$cachedApiKeyRows = $fromTable;
            self::$cachedApiKeyRowsAt = $now;
            return self::$cachedApiKeyRows;
        }

        $raw = $this->getSettingRaw('API_KEY');
        if ($raw === null) {
            $envValue = env('API_KEY', null);
            $raw = $envValue !== null ? (string)$envValue : null;
        }

        $legacyKeys = $raw !== null ? $this->parseApiKeys($raw) : [];
        if ($legacyKeys) {
            $this->writeApiKeysToTable($legacyKeys);
            $fromTable2 = $this->readApiKeyRowsFromTable();
            self::$cachedApiKeyRows = $fromTable2 ?: [];
            self::$cachedApiKeyRowsAt = $now;
            return self::$cachedApiKeyRows;
        }

        self::$cachedApiKeyRows = [];
        self::$cachedApiKeyRowsAt = $now;
        return self::$cachedApiKeyRows;
    }

    public function handle($request, \Closure $next)
    {
        // 确保至少有一个 API Key 存在（首次启动时可能需要迁移）
        $rows = $this->getApiKeyRows();
        if (!$rows) {
            return json([
                'code' => 500,
                'msg' => 'Service not initialized: API key missing'
            ], 500);
        }
        
        $authorization = $request->header('Authorization');
        
        if (empty($authorization) || !preg_match('/^Bearer\s+(.*)$/', $authorization, $matches)) {
            return json([
                'code' => 401,
                'msg' => 'Unauthorized: Invalid Authorization header format'
            ], 401);
        }
        
        $providedKey = trim((string)$matches[1]);
        $providedHash = hash('sha256', $providedKey);

        $apiKeyId = 0;
        try {
            $id = Db::name('api_keys')->where('hash', $providedHash)->value('id');
            $apiKeyId = $id !== null ? (int)$id : 0;
        } catch (\Throwable $e) {
            $apiKeyId = 0;
        }

        if ($apiKeyId <= 0) {
            return json([
                'code' => 401,
                'msg' => 'Unauthorized: Invalid API key'
            ], 401);
        }

        $defaultId = $this->getDefaultApiKeyId();
        $request->withMiddleware([
            'api_key_id' => $apiKeyId,
            'api_key_is_default' => $defaultId > 0 && $apiKeyId === $defaultId,
        ]);
        
        return $next($request);
    }
}

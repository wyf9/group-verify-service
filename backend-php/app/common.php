<?php
// 应用公共文件
use think\facade\Cache;
use think\facade\Db;

if (!function_exists('curl')) {
    /**
     * 发起 HTTP 请求（cURL 封装）
     * @param string $url 请求地址
     * @param array|string $data POST 数据
     * @param int $timeout 超时秒数
     * @param string $method 请求方法
     * @return array ['http_code' => int, 'content' => string, 'error' => string]
     */
    function curl(string $url, $data = [], int $timeout = 10, string $method = 'GET'): array
    {
        $ch = curl_init();
        curl_setopt($ch, CURLOPT_URL, $url);
        curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
        curl_setopt($ch, CURLOPT_TIMEOUT, $timeout);
        curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
        curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);

        if (strtoupper($method) === 'POST') {
            curl_setopt($ch, CURLOPT_POST, true);
            if (is_array($data)) {
                $postBody = http_build_query($data);
            } else {
                $postBody = (string)$data;
            }
            curl_setopt($ch, CURLOPT_POSTFIELDS, $postBody);
            curl_setopt($ch, CURLOPT_HTTPHEADER, ['Content-Type: application/x-www-form-urlencoded']);
        }

        $content = curl_exec($ch);
        $httpCode = (int)curl_getinfo($ch, CURLINFO_HTTP_CODE);
        $error = curl_error($ch);
        curl_close($ch);

        return [
            'http_code' => $httpCode,
            'content' => $content !== false ? (string)$content : '',
            'error' => $error,
        ];
    }
}

function detect_settings_field(): string
{
    static $field = null;
    if ($field !== null) {
        return $field;
    }

    ensure_settings_table();

    try {
        Db::name('settings')->where('name', '__probe__')->limit(1)->value('id');
        $field = 'name';
    } catch (\Throwable $e) {
        $field = 'key';
    }

    return $field;
}

function ensure_settings_table(): void
{
    static $ready = false;
    if ($ready) {
        return;
    }

    try {
        Db::name('settings')->where('id', '>', 0)->limit(1)->value('id');
        $ready = true;
        return;
    } catch (\Throwable) {
    }

    try {
        try {
            Db::execute('CREATE TABLE IF NOT EXISTS `settings` (
                `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                `name` VARCHAR(128) NOT NULL UNIQUE,
                `value` TEXT NOT NULL,
                `created_at` INTEGER UNSIGNED NOT NULL,
                `updated_at` INTEGER UNSIGNED NOT NULL
            )');
            Db::execute('CREATE INDEX IF NOT EXISTS `idx_settings_name` ON `settings` (`name`)');
        } catch (\Throwable) {
            Db::execute('CREATE TABLE IF NOT EXISTS `settings` (
                `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                `name` VARCHAR(128) NOT NULL UNIQUE,
                `value` TEXT NOT NULL,
                `created_at` INT UNSIGNED NOT NULL,
                `updated_at` INT UNSIGNED NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
        }
    } catch (\Throwable) {
    }

    $ready = true;
}

function ensure_api_keys_table(): void
{
    static $ready = false;
    if ($ready) {
        return;
    }

    try {
        Db::name('api_keys')->where('id', '>', 0)->limit(1)->value('id');
        $ready = true;
        return;
    } catch (\Throwable) {
    }

    try {
        try {
            Db::execute('CREATE TABLE IF NOT EXISTS `api_keys` (
                `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                `hash` TEXT NOT NULL,
                `created_at` INTEGER UNSIGNED NOT NULL,
                `updated_at` INTEGER UNSIGNED NOT NULL
            )');
            Db::execute('CREATE UNIQUE INDEX IF NOT EXISTS `uniq_api_keys_hash` ON `api_keys` (`hash`)');
        } catch (\Throwable) {
            Db::execute('CREATE TABLE IF NOT EXISTS `api_keys` (
                `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                `hash` VARCHAR(64) NOT NULL,
                `created_at` INT UNSIGNED NOT NULL,
                `updated_at` INT UNSIGNED NOT NULL,
                UNIQUE KEY `uniq_api_keys_hash` (`hash`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
        }
    } catch (\Throwable) {
    }

    // 迁移旧的明文 value 字段到 hash 字段
    try {
        $hasValue = false;
        try {
            Db::query('SELECT `value` FROM `api_keys` LIMIT 1');
            $hasValue = true;
        } catch (\Throwable) {
        }
        if ($hasValue) {
            $rows = Db::name('api_keys')->whereNull('hash')->whereOr('hash', '')->select()->toArray();
            foreach ($rows as $r) {
                $v = trim((string)($r['value'] ?? ''));
                if ($v === '') continue;
                $h = hash('sha256', $v);
                Db::name('api_keys')->where('id', (int)$r['id'])->update(['hash' => $h]);
            }
        }
    } catch (\Throwable) {
    }

    $ready = true;
}

function ensure_api_call_logs_table(): void
{
    static $ready = false;
    if ($ready) {
        return;
    }

    try {
        Db::name('api_call_logs')->where('id', '>', 0)->limit(1)->value('id');
        $ready = true;
        return;
    } catch (\Throwable) {
    }

    try {
        try {
            Db::execute('CREATE TABLE IF NOT EXISTS `api_call_logs` (
                `id` INTEGER PRIMARY KEY AUTOINCREMENT,
                `api_key_id` INTEGER DEFAULT NULL,
                `endpoint` TEXT NOT NULL,
                `method` VARCHAR(8) NOT NULL,
                `status_code` INTEGER UNSIGNED NOT NULL,
                `group_id` VARCHAR(64) DEFAULT NULL,
                `user_id` VARCHAR(64) DEFAULT NULL,
                `ticket` VARCHAR(64) DEFAULT NULL,
                `code` VARCHAR(10) DEFAULT NULL,
                `ip` VARCHAR(45) DEFAULT NULL,
                `user_agent` VARCHAR(500) DEFAULT NULL,
                `duration_ms` INTEGER UNSIGNED NOT NULL DEFAULT 0,
                `created_at` INTEGER UNSIGNED NOT NULL
            )');
            Db::execute('CREATE INDEX IF NOT EXISTS `idx_api_call_logs_created_at` ON `api_call_logs` (`created_at`)');
            Db::execute('CREATE INDEX IF NOT EXISTS `idx_api_call_logs_api_key` ON `api_call_logs` (`api_key_id`, `created_at`)');
            Db::execute('CREATE INDEX IF NOT EXISTS `idx_api_call_logs_endpoint` ON `api_call_logs` (`created_at`, `endpoint`)');
            Db::execute('CREATE INDEX IF NOT EXISTS `idx_api_call_logs_group` ON `api_call_logs` (`group_id`, `created_at`)');
        } catch (\Throwable) {
            Db::execute('CREATE TABLE IF NOT EXISTS `api_call_logs` (
                `id` INT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                `api_key_id` INT UNSIGNED NULL,
                `endpoint` VARCHAR(255) NOT NULL,
                `method` VARCHAR(8) NOT NULL,
                `status_code` INT UNSIGNED NOT NULL,
                `group_id` VARCHAR(64) NULL,
                `user_id` VARCHAR(64) NULL,
                `ticket` VARCHAR(64) NULL,
                `code` VARCHAR(10) NULL,
                `ip` VARCHAR(45) NULL,
                `user_agent` VARCHAR(500) NULL,
                `duration_ms` INT UNSIGNED NOT NULL DEFAULT 0,
                `created_at` INT UNSIGNED NOT NULL,
                KEY `idx_api_call_logs_created_at` (`created_at`),
                KEY `idx_api_call_logs_api_key` (`api_key_id`, `created_at`),
                KEY `idx_api_call_logs_endpoint` (`created_at`, `endpoint`),
                KEY `idx_api_call_logs_group` (`group_id`, `created_at`)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4');
        }
    } catch (\Throwable) {
    }

    $ready = true;
}

/**
 * 限流检查
 * 
 * 注意：生产环境强烈建议配置 Redis 作为缓存驱动。
 * 文件锁回退方案在高并发下存在竞态窗口，无法保证精确限流。
 */
function rate_limit_hit(string $key, int $limit, int $windowSeconds): int
{
    $k = trim($key);
    if ($k === '' || $limit <= 0 || $windowSeconds <= 0) {
        return 0;
    }

    $now = time();

    // 尝试使用 Redis 原子操作（如果可用）
    $store = Cache::store();
    $handler = null;
    try {
        $handler = $store->handler();
    } catch (\Throwable $e) {
    }

    if ($handler instanceof \Redis) {
        try {
            $count = $handler->incr($k);
            if ($count === 1) {
                $handler->expire($k, $windowSeconds);
            }
            if ($count > $limit) {
                $ttl = $handler->ttl($k);
                return max(1, $ttl > 0 ? $ttl : 1);
            }
            return 0;
        } catch (\Throwable $e) {
            // Redis 不可用时回退到文件缓存
        }
    }

    // 回退方案：文件锁 + 文件缓存（尽力而为的降级限流，非绝对精确但显著减少竞态）
    $lockFile = runtime_path() . 'lock' . DIRECTORY_SEPARATOR . md5($k) . '.lock';
    $lockDir = dirname($lockFile);
    if (!is_dir($lockDir)) {
        @mkdir($lockDir, 0755, true);
    }

    // 定期清理过期 lock 文件（概率触发，约 1% 请求执行清理）
    if (random_int(1, 100) === 1) {
        try {
            $lockFiles = glob($lockDir . DIRECTORY_SEPARATOR . '*.lock');
            if (is_array($lockFiles)) {
                $staleThreshold = $now - $windowSeconds * 2;
                foreach ($lockFiles as $lf) {
                    if (@filemtime($lf) < $staleThreshold) {
                        @unlink($lf);
                    }
                }
            }
        } catch (\Throwable $e) {
        }
    }

    $fp = @fopen($lockFile, 'c');
    if ($fp === false) {
        // 无法获取锁文件时降级为无锁模式
        $data = Cache::get($k, null);
        $count = 0;
        $expireAt = 0;
        if (is_array($data)) {
            $count = (int)($data['count'] ?? 0);
            $expireAt = (int)($data['expire_at'] ?? 0);
        }
        if ($expireAt <= $now) {
            Cache::set($k, ['count' => 1, 'expire_at' => $now + $windowSeconds], $windowSeconds);
            return 0;
        }
        if ($count >= $limit) {
            return max(1, $expireAt - $now);
        }
        Cache::set($k, ['count' => $count + 1, 'expire_at' => $expireAt], $expireAt - $now);
        return 0;
    }

    flock($fp, LOCK_EX);
    try {
        $data = Cache::get($k, null);
        $count = 0;
        $expireAt = 0;
        if (is_array($data)) {
            $count = (int)($data['count'] ?? 0);
            $expireAt = (int)($data['expire_at'] ?? 0);
        }

        if ($expireAt <= $now) {
            $expireAt = $now + $windowSeconds;
            Cache::set($k, ['count' => 1, 'expire_at' => $expireAt], $windowSeconds);
            return 0;
        }

        if ($count >= $limit) {
            return max(1, $expireAt - $now);
        }

        Cache::set($k, ['count' => $count + 1, 'expire_at' => $expireAt], $expireAt - $now);
        return 0;
    } finally {
        flock($fp, LOCK_UN);
        fclose($fp);
    }
}

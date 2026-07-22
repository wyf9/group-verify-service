<?php
namespace app\controller;

use app\BaseController;
use app\traits\ApiKeyTrait;
use think\facade\Db;

class AdminApiKeysController extends BaseController
{
    use ApiKeyTrait;

    public function list()
    {
        $this->ensureApiKeysMigrated();
        $defaultId = $this->getDefaultApiKeyId();

        $sid = '';
        try {
            $sid = trim((string)$this->request->get('id', ''));
        } catch (\Throwable $e) {
            $sid = '';
        }
        $filterId = 0;
        if ($sid !== '') {
            if (!ctype_digit($sid)) {
                return json(['code' => 400, 'msg' => '参数错误'], 400);
            }
            $filterId = (int)$sid;
        }

        try {
            $query = Db::name('api_keys');
            if ($filterId > 0) {
                $query = $query->where('id', $filterId);
            }
            $rows = $query->order('id', 'desc')->select()->toArray();
        } catch (\Throwable $e) {
            $rows = [];
        }

        $items = [];
        foreach ($rows ?: [] as $r) {
            $id = (int)($r['id'] ?? 0);
            $h = (string)($r['hash'] ?? '');
            $items[] = [
                'id' => $id,
                'is_default' => $defaultId > 0 && $id === $defaultId,
                'masked' => $h !== '' ? ('Key#' . $id . ' (' . mb_substr($h, 0, 4) . '...' . mb_substr($h, -4) . ')') : '',
                'note' => (string)($r['note'] ?? ''),
                'enabled' => !array_key_exists('enabled', $r) || (int)$r['enabled'] === 1,
                'last_used_at' => isset($r['last_used_at']) && $r['last_used_at'] !== null ? (int)$r['last_used_at'] : null,
                'request_count' => (int)($r['request_count'] ?? 0),
                'created_at' => (int)($r['created_at'] ?? 0),
                'updated_at' => (int)($r['updated_at'] ?? 0),
            ];
        }

        return json(['code' => 0, 'msg' => 'success', 'data' => ['items' => $items]]);
    }

    public function create()
    {
        $this->ensureApiKeysMigrated();
        $body = $this->getJsonBody();
        $value = trim((string)($body['value'] ?? ''));
        $note = mb_substr(trim((string)($body['note'] ?? '')), 0, 255);

        if ($value === '') {
            try {
                $value = bin2hex(random_bytes(32));
            } catch (\Throwable $e) {
                $value = hash('sha256', uniqid('api_key', true) . microtime(true));
            }
        }

        if (mb_strlen($value) < 16) {
            return json(['code' => 400, 'msg' => '密钥长度至少 16 位'], 400);
        }

        $keyHash = hash('sha256', $value);
        $ts = time();
        try {
            Db::name('api_keys')->insert([
                'hash' => $keyHash,
                'note' => $note,
                'enabled' => 1,
                'request_count' => 0,
                'created_at' => $ts,
                'updated_at' => $ts,
            ]);
        } catch (\Throwable $e) {
            try {
                $exists = Db::name('api_keys')->where('hash', $keyHash)->value('id');
                if ($exists !== null) {
                    return json(['code' => 409, 'msg' => '密钥已存在'], 409);
                }
            } catch (\Throwable $e2) {
            }
            return json(['code' => 500, 'msg' => '创建失败'], 500);
        }

        $id = 0;
        try {
            $id = (int)Db::name('api_keys')->where('hash', $keyHash)->value('id');
        } catch (\Throwable $e) {
        }

        return json([
            'code' => 0,
            'msg' => 'success',
            'data' => [
                'id' => $id,
                'value' => $value,
                'masked' => $this->maskSecret($value),
                'note' => $note,
                'created_at' => $ts,
                'updated_at' => $ts,
            ],
        ])->header(['Cache-Control' => 'no-store']);
    }

    public function update($id = '')
    {
        $this->ensureApiKeysMigrated();
        $sid = trim((string)$id);
        if ($sid === '' || !ctype_digit($sid)) {
            return json(['code' => 400, 'msg' => '参数错误'], 400);
        }
        $targetId = (int)$sid;

        $row = null;
        try {
            $row = Db::name('api_keys')->where('id', $targetId)->find();
        } catch (\Throwable $e) {
            $row = null;
        }
        if (!is_array($row)) {
            return json(['code' => 404, 'msg' => '不存在'], 404);
        }

        $body = $this->getJsonBody();
        $update = ['updated_at' => time()];

        if (array_key_exists('note', $body)) {
            $update['note'] = mb_substr(trim((string)($body['note'] ?? '')), 0, 255);
        }
        if (array_key_exists('enabled', $body)) {
            $enabled = !empty($body['enabled']);
            if (!$enabled && $targetId === $this->getDefaultApiKeyId()) {
                return json(['code' => 403, 'msg' => '当前使用的 API Key 不可禁用'], 403);
            }
            $update['enabled'] = $enabled ? 1 : 0;
        }

        try {
            Db::name('api_keys')->where('id', $targetId)->update($update);
        } catch (\Throwable $e) {
            return json(['code' => 500, 'msg' => '更新失败'], 500);
        }

        \app\middleware\ApiAuth::clearCache();

        return json([
            'code' => 0,
            'msg' => 'success',
            'data' => [
                'id' => $targetId,
                'note' => (string)($update['note'] ?? ($row['note'] ?? '')),
                'enabled' => isset($update['enabled']) ? (int)$update['enabled'] === 1 : (!array_key_exists('enabled', $row) || (int)$row['enabled'] === 1),
                'updated_at' => (int)$update['updated_at'],
            ],
        ]);
    }

    public function delete($id = '')
    {
        $this->ensureApiKeysMigrated();
        $sid = trim((string)$id);
        if ($sid === '' || !ctype_digit($sid)) {
            return json(['code' => 400, 'msg' => '参数错误'], 400);
        }

        $defaultId = $this->getDefaultApiKeyId();
        if ($defaultId > 0 && (int)$sid === $defaultId) {
            return json(['code' => 403, 'msg' => '当前使用的 API Key 不可删除'], 403);
        }

        $n = 0;
        try {
            $n = (int)Db::name('api_keys')->where('id', (int)$sid)->delete();
        } catch (\Throwable $e) {
            $n = 0;
        }

        if ($n <= 0) {
            return json(['code' => 404, 'msg' => '不存在'], 404);
        }

        return json(['code' => 0, 'msg' => 'success', 'data' => ['deleted' => $n]]);
    }

    public function reset($id = '')
    {
        $this->ensureApiKeysMigrated();
        $sid = trim((string)$id);
        if ($sid === '' || !ctype_digit($sid)) {
            return json(['code' => 400, 'msg' => '参数错误'], 400);
        }

        $targetId = (int)$sid;
        if ($targetId <= 0) {
            return json(['code' => 400, 'msg' => '参数错误'], 400);
        }

        if ($targetId === $this->getDefaultApiKeyId() && !allow_config_modify()) {
            return json(['code' => 403, 'msg' => '配置修改已被禁用（ALLOW_CONFIG_MODIFY=false）'], 403);
        }

        $newValue = '';
        $updated = 0;
        $ts = time();
        for ($i = 0; $i < 3; $i++) {
            try {
                try {
                    $newValue = bin2hex(random_bytes(32));
                } catch (\Throwable $e) {
                    $newValue = hash('sha256', uniqid('api_key', true) . microtime(true) . $i);
                }

                $newHash = hash('sha256', $newValue);
                $updated = (int)Db::name('api_keys')->where('id', $targetId)->update([
                    'hash' => $newHash,
                    'updated_at' => $ts,
                ]);
                if ($updated > 0) {
                    break;
                }
            } catch (\Throwable $e) {
                $updated = 0;
            }
        }

        if ($updated <= 0 || $newValue === '') {
            return json(['code' => 500, 'msg' => '重置失败'], 500);
        }

        self::$traitCachedDefaultIdAt = 0;
        \app\middleware\ApiAuth::clearCache();

        return json([
            'code' => 0,
            'msg' => 'success',
            'data' => [
                'id' => $targetId,
                'value' => $newValue,
                'masked' => $this->maskSecret($newValue),
                'updated_at' => $ts,
            ],
        ])->header(['Cache-Control' => 'no-store']);
    }
}

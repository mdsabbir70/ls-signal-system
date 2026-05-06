<?php
/**
 * Bot API Client
 * Calls the Python Flask REST API endpoints.
 */

function bot_api(string $method, string $endpoint, array $data = []): array {
    $url = rtrim(BOT_API_URL, '/') . $endpoint;

    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL            => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT        => 10,
        CURLOPT_HTTPHEADER     => [
            'X-API-Key: ' . BOT_API_KEY,
            'Content-Type: application/json',
            'Accept: application/json',
        ],
    ]);

    if ($method === 'POST') {
        curl_setopt($ch, CURLOPT_POST, true);
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($data));
    } elseif ($method === 'DELETE') {
        curl_setopt($ch, CURLOPT_CUSTOMREQUEST, 'DELETE');
    }

    $body   = curl_exec($ch);
    $status = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    $error  = curl_error($ch);
    curl_close($ch);

    if ($error) {
        return ['success' => false, 'error' => "cURL error: $error", 'data' => null];
    }

    $decoded = json_decode($body, true);
    if (json_last_error() !== JSON_ERROR_NONE) {
        return ['success' => false, 'error' => 'Invalid JSON response', 'data' => null];
    }

    return ['success' => ($status >= 200 && $status < 300), 'data' => $decoded, 'status' => $status];
}

function bot_get(string $endpoint): array {
    return bot_api('GET', $endpoint);
}

function bot_post(string $endpoint, array $data = []): array {
    return bot_api('POST', $endpoint, $data);
}

function bot_delete(string $endpoint): array {
    return bot_api('DELETE', $endpoint);
}

function get_bot_status(): ?array {
    $result = bot_get('/api/status');
    return $result['success'] ? $result['data'] : null;
}

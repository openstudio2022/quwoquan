// Package cache 清理账号注销后不再可信的 Redis 派生状态。
package cache

import (
	"context"
	"errors"
	"fmt"
	"strings"

	rtredis "quwoquan_service/runtime/redis"
)

// ClosedAccountCache 只负责 best-effort 派生缓存失效；PostgreSQL 安全终态
// 已在调用前提交，任何 Redis 错误都不得改变注销结果。
type ClosedAccountCache struct {
	client rtredis.Client
}

func NewClosedAccountCache(client rtredis.Client) *ClosedAccountCache {
	return &ClosedAccountCache{client: client}
}

func (cache *ClosedAccountCache) InvalidateClosedAccount(
	ctx context.Context,
	accountID string,
	phoneCredentialKeys []string,
) error {
	if cache == nil || cache.client == nil {
		return errors.New("closed account cache client is unavailable")
	}
	accountID = strings.TrimSpace(accountID)
	keys := []string{
		fmt.Sprintf("cache:user_profile:%s", accountID),
		fmt.Sprintf("device_tokens:%s", accountID),
		fmt.Sprintf("login_fail:%s", accountID),
	}
	seenPhones := make(map[string]struct{}, len(phoneCredentialKeys))
	for _, raw := range phoneCredentialKeys {
		phone := strings.TrimSpace(raw)
		if phone == "" {
			continue
		}
		if _, exists := seenPhones[phone]; exists {
			continue
		}
		seenPhones[phone] = struct{}{}
		// storage.yaml 只声明 phoneDigest 维度的发码冷却/配额键；
		// 不得按明文手机号拼 key，否则注销后同一号码仍被限流。
		keys = append(
			keys,
			otpResendKey(phone),
			otpQuotaKey(phone),
			otpQuotaDeadlineKey(phone),
		)
	}

	var failures []error
	for _, key := range keys {
		if err := cache.client.Del(ctx, key); err != nil {
			// 不包装 key：账号 id 与手机号不得进入错误或日志。
			failures = append(failures, errors.New("delete closed account cache key"))
		}
	}
	return errors.Join(failures...)
}

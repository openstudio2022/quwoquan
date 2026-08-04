package cache

import (
	"context"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	// otpResendWindow 是两次发码的最小间隔（防刷）。
	otpResendWindow = 60 * time.Second
	// otpHourlyLimit 是单号码每小时最大发码次数。
	otpHourlyLimit = 5
	otpHourWindow  = time.Hour
)

// OtpCodeCache 只在 Redis 承载手机号发码冷却与每小时配额，不持久化 OTP。
type OtpCodeCache struct {
	client rtredis.Client
}

func NewOtpCodeCache(client rtredis.Client) *OtpCodeCache {
	return &OtpCodeCache{client: client}
}

func otpResendKey(phone string) string { return fmt.Sprintf("otp:resend:%s", phone) }
func otpQuotaKey(phone string) string  { return fmt.Sprintf("otp:quota:%s", phone) }

// AllowSend 同时校验「发码冷却」与「每小时配额」。
// 返回 allowed=false 时附带 retryAfterSeconds 供上层提示。
func (c *OtpCodeCache) AllowSend(ctx context.Context, phone string) (bool, int, error) {
	ok, err := c.client.SetNX(ctx, otpResendKey(phone), "1", otpResendWindow)
	if err != nil {
		return false, 0, err
	}
	if !ok {
		return false, int(otpResendWindow / time.Second), nil
	}
	n, err := c.client.Incr(ctx, otpQuotaKey(phone))
	if err != nil {
		return false, 0, err
	}
	if n == 1 {
		_ = c.client.Expire(ctx, otpQuotaKey(phone), otpHourWindow)
	}
	if n > otpHourlyLimit {
		return false, int(otpHourWindow / time.Second), nil
	}
	return true, 0, nil
}

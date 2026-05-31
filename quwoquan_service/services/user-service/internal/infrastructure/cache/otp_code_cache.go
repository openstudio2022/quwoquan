package cache

import (
	"context"
	"errors"
	"fmt"
	"time"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	// otpCodeTTL 是验证码有效期，超时按「已过期」处理。
	otpCodeTTL = 5 * time.Minute
	// otpResendWindow 是两次发码的最小间隔（防刷）。
	otpResendWindow = 60 * time.Second
	// otpHourlyLimit 是单号码每小时最大发码次数。
	otpHourlyLimit = 5
	otpHourWindow  = time.Hour
)

// OtpCodeCache 用 Redis 承载手机号验证码、发码冷却与每小时配额。
// 它是「哑」存储：是否过期/是否匹配的判定交给 application 层。
type OtpCodeCache struct {
	client rtredis.Client
}

func NewOtpCodeCache(client rtredis.Client) *OtpCodeCache {
	return &OtpCodeCache{client: client}
}

func otpCodeKey(phone string) string   { return fmt.Sprintf("otp:code:%s", phone) }
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

func (c *OtpCodeCache) SaveCode(ctx context.Context, phone, code string) error {
	return c.client.Set(ctx, otpCodeKey(phone), code, otpCodeTTL)
}

// ReadCode 返回 (code, found, err)。键不存在（含已过期）时 found=false。
func (c *OtpCodeCache) ReadCode(ctx context.Context, phone string) (string, bool, error) {
	val, err := c.client.Get(ctx, otpCodeKey(phone))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return val, true, nil
}

func (c *OtpCodeCache) ClearCode(ctx context.Context, phone string) error {
	return c.client.Del(ctx, otpCodeKey(phone))
}

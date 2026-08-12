package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
)

const (
	// otpResendWindow 是两次发码的最小间隔（防刷）。
	otpResendWindow = 60 * time.Second
	// otpHourlyLimit 是单号码每小时最大发码次数。
	otpHourlyLimit       = 5
	otpHourWindow        = time.Hour
	otpIdempotencyWindow = 24 * time.Hour
	otpAdmissionClaimTTL = 10 * time.Second
	otpAdmissionWait     = 3 * time.Second
)

var errOtpAdmissionInProgress = errors.New("otp admission is in progress")

// OtpCodeCache 只在 Redis 承载手机号发码冷却与每小时配额，不持久化 OTP。
type OtpCodeCache struct {
	client rtredis.Client
}

func NewOtpCodeCache(client rtredis.Client) *OtpCodeCache {
	return &OtpCodeCache{client: client}
}

func otpPhoneDigest(phone string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(phone)))
	return hex.EncodeToString(sum[:])
}

func otpResendKey(phone string) string {
	return fmt.Sprintf("otp:resend:%s", otpPhoneDigest(phone))
}

func otpQuotaKey(phone string) string {
	return fmt.Sprintf("otp:quota:%s", otpPhoneDigest(phone))
}

func otpQuotaDeadlineKey(phone string) string {
	return fmt.Sprintf("otp:quota-deadline:%s", otpPhoneDigest(phone))
}

func otpIdempotencyKey(key string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(key)))
	return fmt.Sprintf("otp:idempotency:%s", hex.EncodeToString(sum[:]))
}

type otpAdmissionRecord struct {
	CommandFingerprint string `json:"commandFingerprint"`
	State              string `json:"state"`
	Allowed            bool   `json:"allowed"`
	RetryUntilUnixMs   int64  `json:"retryUntilUnixMs"`
}

// AllowSend 同时校验「发码冷却」与「每小时配额」。
// 返回 allowed=false 时附带 retryAfterSeconds 供上层提示。
func (c *OtpCodeCache) AllowSend(
	ctx context.Context,
	phone string,
	idempotencyKey string,
	commandFingerprint string,
) (accountapp.OtpSendAdmission, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	commandFingerprint = strings.TrimSpace(commandFingerprint)
	if idempotencyKey == "" || commandFingerprint == "" {
		return accountapp.OtpSendAdmission{}, errors.New("otp admission identity is required")
	}
	now := time.Now().UTC()
	if replay, found, err := c.loadOrWaitAdmission(
		ctx,
		idempotencyKey,
		commandFingerprint,
		now,
	); err != nil || found {
		return replay, err
	}
	pendingBytes, err := json.Marshal(otpAdmissionRecord{
		CommandFingerprint: commandFingerprint,
		State:              "pending",
	})
	if err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	claimed, err := c.client.SetNX(
		ctx,
		otpIdempotencyKey(idempotencyKey),
		string(pendingBytes),
		otpAdmissionClaimTTL,
	)
	if err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	if !claimed {
		return c.waitForAdmission(
			ctx,
			idempotencyKey,
			commandFingerprint,
		)
	}
	finalized := false
	cooldownOwned := false
	defer func() {
		if !finalized {
			_ = c.client.Del(context.Background(), otpIdempotencyKey(idempotencyKey))
			if cooldownOwned {
				_ = c.client.Del(context.Background(), otpResendKey(phone))
			}
		}
	}()
	retryUntil := now.Add(otpResendWindow)
	ok, err := c.client.SetNX(
		ctx,
		otpResendKey(phone),
		fmt.Sprintf("%d", retryUntil.UnixMilli()),
		otpResendWindow,
	)
	if err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	if !ok {
		remaining, remainingErr := c.remainingCooldown(ctx, phone, now)
		if remainingErr != nil {
			return accountapp.OtpSendAdmission{}, remainingErr
		}
		result := accountapp.OtpSendAdmission{
			RetryAfterSeconds: remaining,
		}
		if err := c.finalizeAdmission(
			ctx,
			idempotencyKey,
			commandFingerprint,
			result,
			now.Add(time.Duration(remaining)*time.Second),
		); err != nil {
			return accountapp.OtpSendAdmission{}, err
		}
		finalized = true
		return result, nil
	}
	cooldownOwned = true
	quotaUntil := now.Add(otpHourWindow)
	quotaDeadlineCreated, err := c.client.SetNX(
		ctx,
		otpQuotaDeadlineKey(phone),
		fmt.Sprintf("%d", quotaUntil.UnixMilli()),
		otpHourWindow,
	)
	if err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	if !quotaDeadlineCreated {
		encoded, deadlineErr := c.client.Get(ctx, otpQuotaDeadlineKey(phone))
		if deadlineErr != nil {
			return accountapp.OtpSendAdmission{}, deadlineErr
		}
		var quotaUntilUnixMs int64
		if _, deadlineErr := fmt.Sscan(encoded, &quotaUntilUnixMs); deadlineErr != nil {
			return accountapp.OtpSendAdmission{}, deadlineErr
		}
		quotaUntil = time.UnixMilli(quotaUntilUnixMs)
	}
	n, err := c.client.Incr(ctx, otpQuotaKey(phone))
	if err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	if n == 1 {
		_ = c.client.Expire(ctx, otpQuotaKey(phone), otpHourWindow)
	}
	if n > otpHourlyLimit {
		_ = c.client.Del(ctx, otpResendKey(phone))
		cooldownOwned = false
		result := accountapp.OtpSendAdmission{
			RetryAfterSeconds: remainingSeconds(quotaUntil.UnixMilli(), now),
		}
		if err := c.finalizeAdmission(
			ctx,
			idempotencyKey,
			commandFingerprint,
			result,
			quotaUntil,
		); err != nil {
			return accountapp.OtpSendAdmission{}, err
		}
		finalized = true
		return result, nil
	}
	result := accountapp.OtpSendAdmission{
		Allowed:           true,
		RetryAfterSeconds: int(otpResendWindow / time.Second),
	}
	if err := c.finalizeAdmission(
		ctx,
		idempotencyKey,
		commandFingerprint,
		result,
		retryUntil,
	); err != nil {
		return accountapp.OtpSendAdmission{}, err
	}
	finalized = true
	return result, nil
}

func (c *OtpCodeCache) finalizeAdmission(
	ctx context.Context,
	idempotencyKey string,
	commandFingerprint string,
	result accountapp.OtpSendAdmission,
	retryUntil time.Time,
) error {
	recordBytes, err := json.Marshal(otpAdmissionRecord{
		CommandFingerprint: commandFingerprint,
		State:              "complete",
		Allowed:            result.Allowed,
		RetryUntilUnixMs:   retryUntil.UnixMilli(),
	})
	if err != nil {
		return err
	}
	return c.client.Set(
		ctx,
		otpIdempotencyKey(idempotencyKey),
		string(recordBytes),
		otpIdempotencyWindow,
	)
}

func (c *OtpCodeCache) loadOrWaitAdmission(
	ctx context.Context,
	idempotencyKey string,
	commandFingerprint string,
	now time.Time,
) (accountapp.OtpSendAdmission, bool, error) {
	result, found, err := c.loadAdmission(
		ctx,
		idempotencyKey,
		commandFingerprint,
		now,
	)
	if found && errors.Is(err, errOtpAdmissionInProgress) {
		result, err = c.waitForAdmission(
			ctx,
			idempotencyKey,
			commandFingerprint,
		)
		return result, true, err
	}
	return result, found, err
}

func (c *OtpCodeCache) waitForAdmission(
	ctx context.Context,
	idempotencyKey string,
	commandFingerprint string,
) (accountapp.OtpSendAdmission, error) {
	timer := time.NewTimer(otpAdmissionWait)
	defer timer.Stop()
	ticker := time.NewTicker(20 * time.Millisecond)
	defer ticker.Stop()
	for {
		result, found, err := c.loadAdmission(
			ctx,
			idempotencyKey,
			commandFingerprint,
			time.Now().UTC(),
		)
		if found && !errors.Is(err, errOtpAdmissionInProgress) {
			return result, err
		}
		if !found {
			return accountapp.OtpSendAdmission{},
				errors.New("otp admission record disappeared while waiting")
		}
		select {
		case <-ctx.Done():
			return accountapp.OtpSendAdmission{}, ctx.Err()
		case <-timer.C:
			return accountapp.OtpSendAdmission{}, errOtpAdmissionInProgress
		case <-ticker.C:
		}
	}
}

func (c *OtpCodeCache) loadAdmission(
	ctx context.Context,
	idempotencyKey string,
	commandFingerprint string,
	now time.Time,
) (accountapp.OtpSendAdmission, bool, error) {
	encoded, err := c.client.Get(ctx, otpIdempotencyKey(idempotencyKey))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return accountapp.OtpSendAdmission{}, false, nil
	}
	if err != nil {
		return accountapp.OtpSendAdmission{}, false, err
	}
	var record otpAdmissionRecord
	if err := json.Unmarshal([]byte(encoded), &record); err != nil {
		return accountapp.OtpSendAdmission{}, false, err
	}
	if record.CommandFingerprint != commandFingerprint {
		return accountapp.OtpSendAdmission{}, true,
			accountapp.ErrOtpIdempotencyConflict
	}
	if record.State == "pending" {
		return accountapp.OtpSendAdmission{}, true, errOtpAdmissionInProgress
	}
	if record.State != "complete" {
		return accountapp.OtpSendAdmission{}, true,
			errors.New("otp admission record state is invalid")
	}
	return accountapp.OtpSendAdmission{
		Allowed:           record.Allowed,
		IdempotentReplay:  true,
		RetryAfterSeconds: remainingSeconds(record.RetryUntilUnixMs, now),
	}, true, nil
}

func (c *OtpCodeCache) remainingCooldown(
	ctx context.Context,
	phone string,
	now time.Time,
) (int, error) {
	encoded, err := c.client.Get(ctx, otpResendKey(phone))
	if errors.Is(err, rtredis.ErrKeyNotFound) {
		return 1, nil
	}
	if err != nil {
		return 0, err
	}
	var retryUntilUnixMs int64
	if _, err := fmt.Sscan(encoded, &retryUntilUnixMs); err != nil {
		return 0, err
	}
	return remainingSeconds(retryUntilUnixMs, now), nil
}

func remainingSeconds(retryUntilUnixMs int64, now time.Time) int {
	remaining := time.UnixMilli(retryUntilUnixMs).Sub(now)
	if remaining <= 0 {
		return 0
	}
	seconds := int((remaining + time.Second - 1) / time.Second)
	if seconds < 1 {
		return 1
	}
	return seconds
}

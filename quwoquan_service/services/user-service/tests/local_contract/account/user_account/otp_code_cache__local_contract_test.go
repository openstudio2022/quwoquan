package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"sync"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	accountapp "quwoquan_service/services/user-service/internal/account/user_account/application/account_orchestration"
	otpcache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
)

const otpHourlyLimit = 5

func TestOtpCodeCacheConcurrentSameKeyConsumesOneAdmission(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	cache := otpcache.NewOtpCodeCache(client)
	const (
		phone       = "+8618038139016"
		key         = "otp-idempotency-0000000000000001"
		fingerprint = "login:+8618038139016"
		workers     = 16
	)

	start := make(chan struct{})
	results := make(chan accountapp.OtpSendAdmission, workers)
	errorsSeen := make(chan error, workers)
	var wait sync.WaitGroup
	for range workers {
		wait.Add(1)
		go func() {
			defer wait.Done()
			<-start
			result, err := cache.AllowSend(ctx, phone, key, fingerprint)
			results <- result
			errorsSeen <- err
		}()
	}
	close(start)
	wait.Wait()
	close(results)
	close(errorsSeen)

	for err := range errorsSeen {
		if err != nil {
			t.Fatalf("same-key admission failed: %v", err)
		}
	}
	allowed := 0
	replayed := 0
	for result := range results {
		if !result.Allowed || result.RetryAfterSeconds < 59 ||
			result.RetryAfterSeconds > 60 {
			t.Fatalf("unexpected admission: %+v", result)
		}
		allowed++
		if result.IdempotentReplay {
			replayed++
		}
	}
	if allowed != workers || replayed != workers-1 {
		t.Fatalf("allowed=%d replayed=%d, want %d/%d", allowed, replayed, workers, workers-1)
	}
	quota, err := client.Get(ctx, otpQuotaStorageKey(phone))
	if err != nil {
		t.Fatalf("read quota: %v", err)
	}
	if quota != "1" {
		t.Fatalf("same key consumed quota %q, want 1", quota)
	}
}

func TestOtpCodeCacheReplayConflictAndExactCooldown(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	cache := otpcache.NewOtpCodeCache(client)
	const phone = "+8618038139016"

	first, err := cache.AllowSend(ctx, phone, "otp-key-00000000000000000001", "login:phone-a")
	if err != nil || !first.Allowed {
		t.Fatalf("first admission = %+v, %v", first, err)
	}
	_, err = cache.AllowSend(
		ctx,
		"+8613900000000",
		"otp-key-00000000000000000001",
		"login:phone-b",
	)
	if !errors.Is(err, accountapp.ErrOtpIdempotencyConflict) {
		t.Fatalf("conflicting replay error = %v", err)
	}

	limited, err := cache.AllowSend(
		ctx,
		phone,
		"otp-key-00000000000000000002",
		"login:phone-a",
	)
	if err != nil || limited.Allowed || limited.RetryAfterSeconds < 59 ||
		limited.RetryAfterSeconds > 60 {
		t.Fatalf("cooldown admission = %+v, %v", limited, err)
	}
	replay, err := cache.AllowSend(
		ctx,
		phone,
		"otp-key-00000000000000000002",
		"login:phone-a",
	)
	if err != nil || replay.Allowed || !replay.IdempotentReplay ||
		replay.RetryAfterSeconds < 59 || replay.RetryAfterSeconds > 60 {
		t.Fatalf("cooldown replay = %+v, %v", replay, err)
	}
}

func TestOtpCodeCacheHourlyLimitReturnsExactRemainingWindow(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	cache := otpcache.NewOtpCodeCache(client)
	const phone = "+8618038139016"
	quotaUntil := time.Now().UTC().Add(37 * time.Second)
	if err := client.Set(ctx, otpQuotaStorageKey(phone), strconv.Itoa(otpHourlyLimit), time.Minute); err != nil {
		t.Fatal(err)
	}
	if err := client.Set(
		ctx,
		otpQuotaDeadlineStorageKey(phone),
		fmt.Sprintf("%d", quotaUntil.UnixMilli()),
		time.Minute,
	); err != nil {
		t.Fatal(err)
	}

	result, err := cache.AllowSend(
		ctx,
		phone,
		"otp-key-00000000000000000003",
		"login:phone-a",
	)
	if err != nil || result.Allowed || result.RetryAfterSeconds < 36 ||
		result.RetryAfterSeconds > 37 {
		t.Fatalf("hour limit admission = %+v, %v", result, err)
	}
}

func otpQuotaStorageKey(phone string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(phone)))
	return "otp:quota:" + hex.EncodeToString(digest[:])
}

func otpQuotaDeadlineStorageKey(phone string) string {
	digest := sha256.Sum256([]byte(strings.TrimSpace(phone)))
	return "otp:quota-deadline:" + hex.EncodeToString(digest[:])
}

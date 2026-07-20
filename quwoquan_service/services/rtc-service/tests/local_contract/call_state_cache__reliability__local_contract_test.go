package local_contract

import (
	"context"
	"testing"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
	rtccache "quwoquan_service/services/rtc-service/internal/infrastructure/cache"
)

func TestCallStateCacheFacetUsesMetadataTTL(t *testing.T) {
	t.Parallel()

	redis := &ttlRecordingRedis{}
	cache := rtccache.NewCallStateCache(redis)
	if err := cache.SetCallState(context.Background(), &model.CallSession{
		ID:     "call-cache-ttl",
		Status: model.StatusRinging,
	}); err != nil {
		t.Fatalf("SetCallState() error = %v", err)
	}
	if redis.key != "cache:rtc:call:call-cache-ttl" {
		t.Fatalf("cache key = %q", redis.key)
	}
	if redis.ttl != 60*time.Second {
		t.Fatalf("cache TTL = %v, want 60s", redis.ttl)
	}
}

type ttlRecordingRedis struct {
	rtredis.Client
	key string
	ttl time.Duration
}

func (r *ttlRecordingRedis) Set(
	_ context.Context,
	key string,
	_ string,
	ttl time.Duration,
) error {
	r.key = key
	r.ttl = ttl
	return nil
}

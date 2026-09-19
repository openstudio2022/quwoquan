package cache

import (
	"context"
	rtredis "quwoquan_service/runtime/redis"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
	"testing"
	"time"
)

func TestProfileCacheGenerationCASMinVersionAndAbsoluteExpiry(t *testing.T) {
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	defer client.Close()
	now := time.Date(2026, 9, 19, 0, 0, 0, 0, time.UTC)
	cache := NewProfileCache(client).WithClock(func() time.Time { return now })
	snap := func(v int) *model.FullSnapshot {
		return &model.FullSnapshot{Profile: &model.UserProfile{UserID: "owner", ProfileVersion: v}}
	}
	if err := cache.Set(ctx, "owner", snap(2)); err != nil {
		t.Fatal(err)
	}
	if err := cache.Set(ctx, "owner", snap(1)); err != nil {
		t.Fatal(err)
	}
	got, err := cache.GetAtLeast(ctx, "owner", 2)
	if err != nil || got == nil || got.Profile.ProfileVersion != 2 {
		t.Fatalf("got=%+v err=%v", got, err)
	}
	if got, err := cache.GetAtLeast(ctx, "owner", 3); err != nil || got != nil {
		t.Fatalf("minVersion bypass got=%+v err=%v", got, err)
	}
	now = now.Add(profileKeyTTL + time.Second)
	if got, err := cache.Get(ctx, "owner"); err != nil || got != nil {
		t.Fatalf("expired source got=%+v err=%v", got, err)
	}
}

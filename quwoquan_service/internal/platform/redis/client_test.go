package redis

import (
	"context"
	"errors"
	"fmt"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	goredis "github.com/redis/go-redis/v9"

	"quwoquan_service/runtime/boundedrecord"
	rtredis "quwoquan_service/runtime/redis"
)

func TestNormalizeXReadGroupBlock(t *testing.T) {
	t.Run("zero_is_non_blocking", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(0); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(0)=%v, want negative sentinel", got)
		}
	})
	t.Run("negative_is_non_blocking", func(t *testing.T) {
		if got := normalizeXReadGroupBlock(-5 * time.Millisecond); got >= 0 {
			t.Fatalf("normalizeXReadGroupBlock(-5ms)=%v, want negative sentinel", got)
		}
	})
	t.Run("positive_timeout_is_preserved", func(t *testing.T) {
		const block = 25 * time.Millisecond
		if got := normalizeXReadGroupBlock(block); got != block {
			t.Fatalf("normalizeXReadGroupBlock(%v)=%v", block, got)
		}
	})
}

func TestBoundedImmutableRecordAtomicLuaCommercialAdmission(t *testing.T) {
	raw, client := newAtomicTestClient(t)
	ctx := context.Background()

	t.Run("owner_eviction_winner_and_cleanup_keep_exact_usage", func(t *testing.T) {
		const tag = "quota-owner"
		policy := boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 4,
			MaximumLiveBytesPerShard:   64,
			MaximumLiveRecordsPerOwner: 2,
		}
		ownerA := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		ownerB := "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
		a1 := atomicRecordKey(tag, ownerA, "01")
		a2 := atomicRecordKey(tag, ownerA, "02")
		a3 := atomicRecordKey(tag, ownerA, "03")
		b1 := atomicRecordKey(tag, ownerB, "01")

		for _, tc := range []struct {
			key     string
			owner   string
			value   string
			evicted int64
			records int64
			bytes   int64
		}{
			{a1, ownerA, "aaaa", 0, 1, 4},
			{a2, ownerA, "bbbbbb", 0, 2, 10},
			{a3, ownerA, "ccc", 1, 2, 9},
			{b1, ownerB, "dddd", 0, 3, 13},
		} {
			result, err := client.CreateBoundedImmutableRecordAtomic(
				ctx,
				atomicRequest(tag, tc.key, tc.owner, tc.value, policy),
			)
			if err != nil || !result.Created || result.Winner != "" ||
				!result.UsageMeasured ||
				result.OwnerEvicted != tc.evicted ||
				result.LiveRecords != tc.records ||
				result.LiveBytes != tc.bytes {
				t.Fatalf("create %q result=%+v err=%v", tc.key, result, err)
			}
		}
		if _, err := client.Get(ctx, a1); !errors.Is(err, rtredis.ErrKeyNotFound) {
			t.Fatalf("oldest owner record error=%v, want not found", err)
		}

		if err := raw.PExpire(ctx, b1, 5*time.Minute).Err(); err != nil {
			t.Fatalf("shorten winner TTL: %v", err)
		}
		ttlBefore, err := raw.PTTL(ctx, b1).Result()
		if err != nil {
			t.Fatalf("winner TTL before replay: %v", err)
		}
		replay, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(tag, b1, ownerB, "different contender", policy),
		)
		if err != nil || replay.Created || replay.Winner != "dddd" ||
			!replay.UsageMeasured ||
			replay.OwnerEvicted != 0 || replay.LiveRecords != 3 ||
			replay.LiveBytes != 13 {
			t.Fatalf("winner replay result=%+v err=%v", replay, err)
		}
		ttlAfter, err := raw.PTTL(ctx, b1).Result()
		if err != nil {
			t.Fatalf("winner TTL after replay: %v", err)
		}
		if ttlAfter > ttlBefore || ttlBefore-ttlAfter > time.Second {
			t.Fatalf("winner replay changed TTL from %v to %v", ttlBefore, ttlAfter)
		}

		// A score at or before Redis server time is expired even if a stale
		// value still exists. The next create removes value/index/metadata and
		// subtracts its bytes before admission.
		if err := raw.ZAdd(
			ctx,
			atomicIndexKey(tag),
			goredis.Z{Score: 0, Member: a2},
		).Err(); err != nil {
			t.Fatalf("mark indexed record expired: %v", err)
		}
		b2 := atomicRecordKey(tag, ownerB, "02")
		cleaned, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(tag, b2, ownerB, "ee", policy),
		)
		if err != nil || !cleaned.Created || !cleaned.UsageMeasured ||
			cleaned.LiveRecords != 3 ||
			cleaned.LiveBytes != 9 {
			t.Fatalf("cleanup create result=%+v err=%v", cleaned, err)
		}
		if _, err := client.Get(ctx, a2); !errors.Is(err, rtredis.ErrKeyNotFound) {
			t.Fatalf("expired indexed value error=%v, want cleanup", err)
		}
		if exists, err := raw.HExists(
			ctx,
			atomicMetadataKey(tag),
			a2,
		).Result(); err != nil || exists {
			t.Fatalf("expired metadata exists=%v err=%v", exists, err)
		}
	})

	t.Run("shard_key_cap_rejects_without_cross_owner_eviction", func(t *testing.T) {
		const tag = "quota-keys"
		policy := boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 2,
			MaximumLiveBytesPerShard:   64,
			MaximumLiveRecordsPerOwner: 2,
		}
		owners := []string{
			"11111111111111111111111111111111",
			"22222222222222222222222222222222",
			"33333333333333333333333333333333",
		}
		for index := 0; index < 2; index++ {
			key := atomicRecordKey(tag, owners[index], "01")
			result, err := client.CreateBoundedImmutableRecordAtomic(
				ctx,
				atomicRequest(tag, key, owners[index], "ok", policy),
			)
			if err != nil || !result.Created {
				t.Fatalf("seed owner %d result=%+v err=%v", index, result, err)
			}
		}
		rejectedKey := atomicRecordKey(tag, owners[2], "01")
		rejected, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(tag, rejectedKey, owners[2], "x", policy),
		)
		if !errors.Is(err, boundedrecord.ErrShardKeyQuota) ||
			!rejected.UsageMeasured ||
			rejected.LiveRecords != 2 || rejected.LiveBytes != 4 {
			t.Fatalf("key rejection result=%+v err=%v", rejected, err)
		}
		for index := 0; index < 2; index++ {
			key := atomicRecordKey(tag, owners[index], "01")
			if value, err := client.Get(ctx, key); err != nil || value != "ok" {
				t.Fatalf("other owner %d value=%q err=%v", index, value, err)
			}
		}
		if _, err := client.Get(ctx, rejectedKey); !errors.Is(err, rtredis.ErrKeyNotFound) {
			t.Fatalf("rejected key error=%v, want not found", err)
		}
	})

	t.Run("shard_byte_cap_rejects_without_mutation", func(t *testing.T) {
		const tag = "quota-bytes"
		policy := boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 4,
			MaximumLiveBytesPerShard:   5,
			MaximumLiveRecordsPerOwner: 2,
		}
		ownerA := "44444444444444444444444444444444"
		ownerB := "55555555555555555555555555555555"
		firstKey := atomicRecordKey(tag, ownerA, "01")
		if result, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(tag, firstKey, ownerA, "four", policy),
		); err != nil || !result.Created {
			t.Fatalf("seed byte quota result=%+v err=%v", result, err)
		}
		rejectedKey := atomicRecordKey(tag, ownerB, "01")
		rejected, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(tag, rejectedKey, ownerB, "xx", policy),
		)
		if !errors.Is(err, boundedrecord.ErrShardByteQuota) ||
			!rejected.UsageMeasured ||
			rejected.LiveRecords != 1 || rejected.LiveBytes != 4 {
			t.Fatalf("byte rejection result=%+v err=%v", rejected, err)
		}
		if value, err := client.Get(ctx, firstKey); err != nil || value != "four" {
			t.Fatalf("existing byte-quota owner value=%q err=%v", value, err)
		}
		if members, err := raw.ZRange(
			ctx,
			atomicIndexKey(tag),
			0,
			int64(policy.MaximumLiveRecordsPerShard),
		).Result(); err != nil || len(members) != 1 {
			t.Fatalf("byte rejection members=%v err=%v", members, err)
		}
	})

	t.Run("index_and_metadata_ttl_never_shorten_below_live_value", func(t *testing.T) {
		const tag = "quota-ttl"
		policy := boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 4,
			MaximumLiveBytesPerShard:   64,
			MaximumLiveRecordsPerOwner: 2,
		}
		ownerA := "99999999999999999999999999999999"
		ownerB := "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
		longRequest := atomicRequest(
			tag,
			atomicRecordKey(tag, ownerA, "01"),
			ownerA,
			"long",
			policy,
		)
		if _, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			longRequest,
		); err != nil {
			t.Fatalf("seed long-lived record: %v", err)
		}
		shortRequest := atomicRequest(
			tag,
			atomicRecordKey(tag, ownerB, "01"),
			ownerB,
			"short",
			policy,
		)
		shortRequest.TTL = time.Minute
		if _, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			shortRequest,
		); err != nil {
			t.Fatalf("append shorter-lived record: %v", err)
		}
		for _, key := range []string{
			atomicIndexKey(tag),
			atomicMetadataKey(tag),
		} {
			ttl, err := raw.PTTL(ctx, key).Result()
			if err != nil {
				t.Fatalf("read %q TTL: %v", key, err)
			}
			if ttl < 9*time.Minute {
				t.Fatalf("%q TTL shortened to %v below live value", key, ttl)
			}
		}
	})

	t.Run("corrupt_oversized_index_fails_at_bounded_prescan", func(t *testing.T) {
		const tag = "quota-repair"
		policy := boundedrecord.Policy{
			ShardCount:                 1,
			MaximumLiveRecordsPerShard: 2,
			MaximumLiveBytesPerShard:   64,
			MaximumLiveRecordsPerOwner: 2,
		}
		for index := 0; index < policy.MaximumLiveRecordsPerShard+1; index++ {
			key := atomicRecordKey(
				tag,
				"66666666666666666666666666666666",
				fmt.Sprintf("%02d", index),
			)
			if err := raw.ZAdd(
				ctx,
				atomicIndexKey(tag),
				goredis.Z{Score: float64(index + 1), Member: key},
			).Err(); err != nil {
				t.Fatalf("seed corrupt index %d: %v", index, err)
			}
		}
		requestKey := atomicRecordKey(
			tag,
			"77777777777777777777777777777777",
			"01",
		)
		_, err := client.CreateBoundedImmutableRecordAtomic(
			ctx,
			atomicRequest(
				tag,
				requestKey,
				"77777777777777777777777777777777",
				"x",
				policy,
			),
		)
		if !errors.Is(err, boundedrecord.ErrRepairBound) {
			t.Fatalf("oversized index error=%v, want repair bound", err)
		}
	})
}

func TestBoundedImmutableRecordAtomicLuaConcurrentCreatesStayBounded(t *testing.T) {
	raw, client := newAtomicTestClient(t)
	ctx := context.Background()
	const (
		tag         = "quota-concurrent"
		owner       = "88888888888888888888888888888888"
		quota       = 8
		createCount = 32
	)
	policy := boundedrecord.Policy{
		ShardCount:                 1,
		MaximumLiveRecordsPerShard: quota,
		MaximumLiveBytesPerShard:   1 << 20,
		MaximumLiveRecordsPerOwner: quota,
	}

	start := make(chan struct{})
	results := make(chan error, createCount)
	evictions := make(chan int64, createCount)
	keys := make([]string, createCount)
	var group sync.WaitGroup
	for index := 0; index < createCount; index++ {
		keys[index] = atomicRecordKey(tag, owner, fmt.Sprintf("%02d", index))
		group.Add(1)
		go func(sequence int) {
			defer group.Done()
			<-start
			result, err := client.CreateBoundedImmutableRecordAtomic(
				ctx,
				atomicRequest(
					tag,
					keys[sequence],
					owner,
					fmt.Sprintf("payload-%02d", sequence),
					policy,
				),
			)
			if err == nil && !result.Created {
				err = errors.New("unique key returned created=false")
			}
			results <- err
			evictions <- result.OwnerEvicted
		}(index)
	}
	close(start)
	group.Wait()
	close(results)
	close(evictions)
	for err := range results {
		if err != nil {
			t.Fatalf("concurrent atomic create: %v", err)
		}
	}
	var evictionTotal int64
	for evicted := range evictions {
		evictionTotal += evicted
	}
	if evictionTotal != createCount-quota {
		t.Fatalf(
			"concurrent owner evictions=%d, want %d",
			evictionTotal,
			createCount-quota,
		)
	}
	members, err := raw.ZRange(
		ctx,
		atomicIndexKey(tag),
		0,
		int64(policy.MaximumLiveRecordsPerShard),
	).Result()
	if err != nil || len(members) != quota {
		t.Fatalf("concurrent members=%d err=%v, want %d", len(members), err, quota)
	}
	metadataCount, err := raw.HLen(ctx, atomicMetadataKey(tag)).Result()
	if err != nil || metadataCount != quota {
		t.Fatalf(
			"concurrent metadata fields=%d err=%v, want %d",
			metadataCount,
			err,
			quota,
		)
	}
	indexed := make(map[string]struct{}, len(members))
	for _, member := range members {
		indexed[member] = struct{}{}
	}
	for _, key := range keys {
		exists, err := raw.Exists(ctx, key).Result()
		if err != nil {
			t.Fatalf("read known value %q: %v", key, err)
		}
		_, isIndexed := indexed[key]
		if (exists == 1) != isIndexed {
			t.Fatalf(
				"value/index orphan for %q: exists=%d indexed=%v",
				key,
				exists,
				isIndexed,
			)
		}
	}
}

func newAtomicTestClient(t *testing.T) (*goredis.Client, *client) {
	t.Helper()
	redisAddress := os.Getenv("QWQ_TEST_REAL_REDIS_ADDR")
	if redisAddress == "" {
		server := miniredis.RunT(t)
		redisAddress = server.Addr()
	}
	raw := goredis.NewClient(&goredis.Options{Addr: redisAddress})
	t.Cleanup(func() { _ = raw.Close() })
	return raw, &client{raw: raw}
}

func atomicRequest(
	tag string,
	recordKey string,
	owner string,
	value string,
	policy boundedrecord.Policy,
) boundedrecord.Request {
	return boundedrecord.Request{
		RecordKey:        recordKey,
		ShardIndexKey:    atomicIndexKey(tag),
		ShardMetadataKey: atomicMetadataKey(tag),
		OwnerDigest:      owner,
		Value:            value,
		TTL:              10 * time.Minute,
		Policy:           policy,
	}
}

func atomicRecordKey(tag, owner, suffix string) string {
	return fmt.Sprintf("rec:bounded:{%s}:%s:%s", tag, owner, suffix)
}

func atomicIndexKey(tag string) string {
	return fmt.Sprintf("rec:bounded_index:{%s}", tag)
}

func atomicMetadataKey(tag string) string {
	return fmt.Sprintf("rec:bounded_metadata:{%s}", tag)
}

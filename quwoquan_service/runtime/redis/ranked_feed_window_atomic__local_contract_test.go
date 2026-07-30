package redis

import (
	"context"
	"errors"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/boundedrecord"
)

func TestRankedFeedWindowAtomicCapabilitySurvivesInstrumentationAndRecommendationAdapter(t *testing.T) {
	client := InstrumentedClient(
		NewMemoryClient(),
		"rec",
		NewMetricsCollector([]string{"rec"}),
	)
	adapter := NewRecAdapter(client)
	creator, ok := adapter.(interface {
		CreateBoundedImmutableRecordAtomic(
			context.Context,
			boundedrecord.Request,
		) (boundedrecord.Result, error)
	})
	if !ok {
		t.Fatal("instrumented recommendation Redis adapter lost atomic window capability")
	}

	ctx := context.Background()
	const (
		indexKey    = "rec:ranked_feed_window_index:{rfw-0000}"
		metadataKey = "rec:ranked_feed_window_metadata:{rfw-0000}"
		quota       = 8
	)
	policy := boundedrecord.Policy{
		ShardCount:                 1,
		MaximumLiveRecordsPerShard: quota,
		MaximumLiveBytesPerShard:   1 << 20,
		MaximumLiveRecordsPerOwner: quota,
	}
	const owner = "0123456789abcdef0123456789abcdef"
	keys := make([]string, 0, quota+1)
	for index := 0; index < quota+1; index++ {
		key := fmt.Sprintf(
			"rec:ranked_feed_window:{rfw-0000}:%s:rfw_%02d",
			owner,
			index,
		)
		keys = append(keys, key)
		result, err := creator.CreateBoundedImmutableRecordAtomic(
			ctx,
			boundedrecord.Request{
				RecordKey:        key,
				ShardIndexKey:    indexKey,
				ShardMetadataKey: metadataKey,
				OwnerDigest:      owner,
				Value:            fmt.Sprintf("payload-%02d", index),
				TTL:              10 * time.Minute,
				Policy:           policy,
			},
		)
		if err != nil || !result.Created || result.Winner != "" ||
			!result.UsageMeasured {
			t.Fatalf(
				"adapter atomic create %d: result=%+v err=%v",
				index,
				result,
				err,
			)
		}
		wantEvicted := int64(0)
		if index == quota {
			wantEvicted = 1
		}
		if result.OwnerEvicted != wantEvicted {
			t.Fatalf(
				"adapter atomic create %d evicted=%d, want %d",
				index,
				result.OwnerEvicted,
				wantEvicted,
			)
		}
	}
	if _, err := adapter.Get(ctx, keys[0]); !errors.Is(err, ErrKeyNotFound) {
		t.Fatalf("adapter oldest window error=%v, want ErrKeyNotFound", err)
	}
	if got, err := adapter.Get(ctx, keys[len(keys)-1]); err != nil || got != "payload-08" {
		t.Fatalf("adapter newest window=(%q,%v), want payload-08", got, err)
	}
}

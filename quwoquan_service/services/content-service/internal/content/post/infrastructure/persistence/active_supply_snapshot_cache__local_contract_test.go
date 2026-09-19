// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feed-fallback-degrade/spec.md#gwt-001
package persistence

import (
	"context"
	"errors"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

func TestActiveSupplySnapshotCacheCachesContentReadySnapshotWithoutPlayableVideo(t *testing.T) {
	key, snapshot, now := activeSupplyCacheFixture()
	if !snapshot.ContentReady() || snapshot.Ready() {
		t.Fatal("fixture must be ContentReady without satisfying playable-video readiness")
	}

	cache := newActiveSupplySnapshotCache(time.Minute, 0)
	cache.now = func() time.Time { return now }
	reads := 0
	read := func(context.Context) (postports.ActiveSupplySnapshot, error) {
		reads++
		return snapshot, nil
	}

	first, err := cache.Load(context.Background(), key, read)
	if err != nil {
		t.Fatalf("first cache load: %v", err)
	}
	second, err := cache.Load(context.Background(), key, read)
	if err != nil {
		t.Fatalf("second cache load: %v", err)
	}
	if first != snapshot || second != snapshot {
		t.Fatalf("cache loads = (%+v, %+v), want snapshot %+v", first, second, snapshot)
	}
	if reads != 1 {
		t.Fatalf("underlying reads = %d, want 1", reads)
	}
}

func TestActiveSupplySnapshotCacheDoesNotCacheEmptyInvalidOrFailedRead(t *testing.T) {
	key, snapshot, now := activeSupplyCacheFixture()
	readFailure := errors.New("read failed")
	tests := []struct {
		name     string
		snapshot postports.ActiveSupplySnapshot
		err      error
	}{
		{name: "empty", snapshot: postports.ActiveSupplySnapshot{}},
		{name: "invalid", snapshot: func() postports.ActiveSupplySnapshot {
			invalid := snapshot
			invalid.Posts = 0
			return invalid
		}()},
		{name: "failed read", snapshot: snapshot, err: readFailure},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			cache := newActiveSupplySnapshotCache(time.Minute, 0)
			cache.now = func() time.Time { return now }
			reads := 0
			read := func(context.Context) (postports.ActiveSupplySnapshot, error) {
				reads++
				return test.snapshot, test.err
			}
			for range 2 {
				_, _ = cache.Load(context.Background(), key, read)
			}
			if reads != 2 {
				t.Fatalf("underlying reads = %d, want 2", reads)
			}
		})
	}
}

func TestActiveSupplySnapshotCacheExpiresContentReadySnapshot(t *testing.T) {
	key, snapshot, now := activeSupplyCacheFixture()
	cache := newActiveSupplySnapshotCache(time.Second, 0)
	cache.now = func() time.Time { return now }
	reads := 0
	read := func(context.Context) (postports.ActiveSupplySnapshot, error) {
		reads++
		return snapshot, nil
	}

	if _, err := cache.Load(context.Background(), key, read); err != nil {
		t.Fatalf("initial cache load: %v", err)
	}
	now = now.Add(time.Second)
	if _, err := cache.Load(context.Background(), key, read); err != nil {
		t.Fatalf("expired cache load: %v", err)
	}
	if reads != 2 {
		t.Fatalf("underlying reads = %d, want 2", reads)
	}
}

func TestActiveSupplySnapshotCacheCoalescesConcurrentContentReadyReads(t *testing.T) {
	key, snapshot, now := activeSupplyCacheFixture()
	cache := newActiveSupplySnapshotCache(time.Minute, 0)
	cache.now = func() time.Time { return now }

	started := make(chan struct{})
	release := make(chan struct{})
	var reads atomic.Int32
	read := func(context.Context) (postports.ActiveSupplySnapshot, error) {
		if reads.Add(1) == 1 {
			close(started)
		}
		<-release
		return snapshot, nil
	}

	const callers = 8
	errs := make(chan error, callers)
	var callersReady sync.WaitGroup
	callersReady.Add(callers)
	start := make(chan struct{})
	for range callers {
		go func() {
			callersReady.Done()
			<-start
			got, err := cache.Load(context.Background(), key, read)
			if err == nil && got != snapshot {
				err = errors.New("coalesced load returned unexpected snapshot")
			}
			errs <- err
		}()
	}
	callersReady.Wait()
	close(start)
	<-started
	time.Sleep(10 * time.Millisecond)
	close(release)
	for range callers {
		if err := <-errs; err != nil {
			t.Fatal(err)
		}
	}
	if got := reads.Load(); got != 1 {
		t.Fatalf("underlying reads = %d, want 1", got)
	}
}

func activeSupplyCacheFixture() (activeSupplyCacheKey, postports.ActiveSupplySnapshot, time.Time) {
	activatedAt := time.Date(2026, time.September, 16, 1, 0, 0, 0, time.UTC)
	key := activeSupplyCacheKey{
		environment:       "alpha",
		releaseID:         "release-current",
		manifestDigest:    "sha256:" + strings.Repeat("a", 64),
		projectionVersion: 17,
		revision:          3,
		activatedAt:       activatedAt,
	}
	return key, postports.ActiveSupplySnapshot{
		Environment:       key.environment,
		SourceOwner:       "qwq_data",
		Status:            "active",
		ActiveReleaseID:   key.releaseID,
		ManifestDigest:    key.manifestDigest,
		ProjectionVersion: key.projectionVersion,
		Revision:          key.revision,
		ActivatedAt:       key.activatedAt,
		ReadbackStatus:    "passed",
		Posts:             4,
		PlayableVideos:    0,
	}, activatedAt.Add(time.Second)
}

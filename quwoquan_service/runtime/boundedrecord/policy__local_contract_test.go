package boundedrecord

import (
	"strings"
	"testing"
	"time"
)

func TestPolicyProvesFamilyWideBoundsAndStableShard(t *testing.T) {
	policy := Policy{
		ShardCount:                 256,
		MaximumLiveRecordsPerShard: 128,
		MaximumLiveBytesPerShard:   128 * 1024 * 1024,
		MaximumLiveRecordsPerOwner: 8,
	}
	if err := policy.Validate(); err != nil {
		t.Fatalf("valid policy: %v", err)
	}
	if policy.MaximumLiveRecords() != 32768 ||
		policy.MaximumLiveBytes() != 32*1024*1024*1024 {
		t.Fatalf("family-wide bounds drifted: %+v", policy)
	}
	digest := strings.Repeat("a", 32)
	first, err := policy.ShardForDigest(digest)
	if err != nil {
		t.Fatalf("map owner digest: %v", err)
	}
	second, err := policy.ShardForDigest(digest)
	if err != nil || first != second || len(first) != 4 {
		t.Fatalf("unstable fixed shard: first=%q second=%q err=%v", first, second, err)
	}
}

func TestPolicyRejectsInvalidOrOverflowingAdmission(t *testing.T) {
	for _, policy := range []Policy{
		{ShardCount: 3, MaximumLiveRecordsPerShard: 8, MaximumLiveBytesPerShard: 8, MaximumLiveRecordsPerOwner: 1},
		{ShardCount: 1, MaximumLiveRecordsPerShard: 1, MaximumLiveBytesPerShard: 1, MaximumLiveRecordsPerOwner: 2},
		{ShardCount: 2, MaximumLiveRecordsPerShard: 1, MaximumLiveBytesPerShard: maximumInt64, MaximumLiveRecordsPerOwner: 1},
	} {
		if err := policy.Validate(); err == nil {
			t.Fatalf("invalid policy passed: %+v", policy)
		}
	}
	validPolicy := Policy{
		ShardCount:                 1,
		MaximumLiveRecordsPerShard: 1,
		MaximumLiveBytesPerShard:   16,
		MaximumLiveRecordsPerOwner: 1,
	}
	request := Request{
		RecordKey:        "value:{quota}",
		ShardIndexKey:    "index:{quota}",
		ShardMetadataKey: "metadata:{quota}",
		OwnerDigest:      "not-a-canonical-digest",
		Value:            "value",
		TTL:              time.Minute,
		Policy:           validPolicy,
	}
	if err := request.Validate(); err == nil {
		t.Fatal("invalid owner digest passed request validation")
	}
	request.OwnerDigest = strings.Repeat("a", 32)
	request.Value = strings.Repeat("x", 17)
	if err := request.Validate(); err == nil {
		t.Fatal("single payload above shard byte cap passed validation")
	}
	request.Value = "value"
	if err := request.Validate(); err != nil {
		t.Fatalf("valid request rejected: %v", err)
	}
	for _, invalidDigest := range []string{
		strings.Repeat("A", 32),
		strings.Repeat("a", 31) + "z",
		strings.Repeat("a", 66),
	} {
		if _, err := validPolicy.ShardForDigest(invalidDigest); err == nil {
			t.Fatalf("invalid canonical digest mapped to shard: %q", invalidDigest)
		}
	}
}

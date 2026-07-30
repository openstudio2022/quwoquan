// Package boundedrecord defines the storage-neutral business admission
// contract for short-lived immutable records. Redis is only the enforcement
// mechanism; maxmemory and eviction policy are deliberately outside this
// contract.
package boundedrecord

import (
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"
)

const (
	// MaximumShardCount bounds both Redis Cluster slot fan-out and metric/config
	// cardinality. ShardCount must be a power of two so a digest maps to one
	// stable shard without a mutable registry.
	MaximumShardCount = 4096
	maximumInt64      = int64(^uint64(0) >> 1)
)

var (
	ErrAtomicUnavailable = errors.New(
		"bounded immutable record atomic operation unavailable",
	)
	ErrShardKeyQuota = errors.New(
		"bounded immutable record shard live-key quota exceeded",
	)
	ErrShardByteQuota = errors.New(
		"bounded immutable record shard live-byte quota exceeded",
	)
	ErrRepairBound = errors.New(
		"bounded immutable record shard index exceeds repair bound",
	)
	ErrConcurrentIndexChange = errors.New(
		"bounded immutable record shard index changed concurrently",
	)
)

// Policy is the complete bounded-admission policy for one immutable-record
// family. Every shard is independent and has the same caps, therefore the
// family-wide hard upper bounds are exactly:
//
//	ShardCount * MaximumLiveRecordsPerShard
//	ShardCount * MaximumLiveBytesPerShard
//
// MaximumLiveRecordsPerOwner is an isolation limit inside one shard. Reaching
// a shard cap rejects the contender and never evicts another owner.
type Policy struct {
	ShardCount                 int
	MaximumLiveRecordsPerShard int
	MaximumLiveBytesPerShard   int64
	MaximumLiveRecordsPerOwner int
}

func (p Policy) Validate() error {
	if p.ShardCount <= 0 || p.ShardCount > MaximumShardCount ||
		p.ShardCount&(p.ShardCount-1) != 0 {
		return fmt.Errorf(
			"bounded immutable record shard count must be a power of two in [1,%d]",
			MaximumShardCount,
		)
	}
	if p.MaximumLiveRecordsPerShard <= 0 ||
		p.MaximumLiveBytesPerShard <= 0 ||
		p.MaximumLiveRecordsPerOwner <= 0 ||
		p.MaximumLiveRecordsPerOwner > p.MaximumLiveRecordsPerShard {
		return errors.New(
			"bounded immutable record live record/byte/owner limits are invalid",
		)
	}
	if int64(p.MaximumLiveRecordsPerShard) >
		maximumInt64/int64(p.ShardCount) ||
		p.MaximumLiveBytesPerShard > maximumInt64/int64(p.ShardCount) {
		return errors.New(
			"bounded immutable record family-wide live limit overflows int64",
		)
	}
	return nil
}

func (p Policy) MaximumLiveRecords() int64 {
	return int64(p.ShardCount) * int64(p.MaximumLiveRecordsPerShard)
}

func (p Policy) MaximumLiveBytes() int64 {
	return int64(p.ShardCount) * p.MaximumLiveBytesPerShard
}

// ShardForDigest maps a canonical hexadecimal SHA-256 digest to one stable,
// fixed-width quota shard. The first 64 bits are sufficient because the digest
// is already uniform and ShardCount is a power of two.
func (p Policy) ShardForDigest(digest string) (string, error) {
	if err := p.Validate(); err != nil {
		return "", err
	}
	digest = strings.TrimSpace(digest)
	if !validOwnerDigest(digest) {
		return "", errors.New("bounded immutable record owner digest is invalid")
	}
	prefix, err := strconv.ParseUint(digest[:16], 16, 64)
	if err != nil {
		return "", errors.New("bounded immutable record owner digest is invalid")
	}
	return fmt.Sprintf("%04x", prefix&uint64(p.ShardCount-1)), nil
}

// Request contains every key Lua may touch. RecordKey, ShardIndexKey and
// ShardMetadataKey must share one Redis Cluster hash tag. The platform adapter
// reads the bounded index and supplies every current record as an explicit
// EVAL key; scripts never construct or access dynamic Redis keys.
type Request struct {
	RecordKey        string
	ShardIndexKey    string
	ShardMetadataKey string
	OwnerDigest      string
	Value            string
	TTL              time.Duration
	Policy           Policy
}

func (r Request) Validate() error {
	if err := r.Policy.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(r.RecordKey) == "" ||
		strings.TrimSpace(r.ShardIndexKey) == "" ||
		strings.TrimSpace(r.ShardMetadataKey) == "" ||
		!validOwnerDigest(r.OwnerDigest) ||
		r.TTL <= 0 || len(r.Value) <= 0 ||
		int64(len(r.Value)) > r.Policy.MaximumLiveBytesPerShard {
		return errors.New("bounded immutable record request is invalid")
	}
	return nil
}

func validOwnerDigest(value string) bool {
	value = strings.TrimSpace(value)
	if len(value) < 16 || len(value) > 64 || len(value)%2 != 0 ||
		value != strings.ToLower(value) {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded)*2 == len(value)
}

// Result is returned for both a newly created record and an idempotent winner.
// When UsageMeasured is true, LiveRecords/LiveBytes were computed from the
// bounded index and metadata in the same atomic operation; there are no mutable
// counters that can drift. Callers must not publish zero-valued usage from an
// unavailable or repair-rejected operation.
type Result struct {
	Winner        string
	Created       bool
	OwnerEvicted  int64
	UsageMeasured bool
	LiveRecords   int64
	LiveBytes     int64
}

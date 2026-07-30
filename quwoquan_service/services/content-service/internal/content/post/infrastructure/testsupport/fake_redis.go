package testsupport

import (
	"context"
	"fmt"
	"sync"
	"time"

	"quwoquan_service/runtime/boundedrecord"
	rtrec "quwoquan_service/runtime/recommendation"
)

// FakeRedis is a deterministic local-contract adapter. Production code cannot
// reach this package because only *_test.go callers import internal/testsupport.
type FakeRedis struct {
	mu             sync.RWMutex
	strings        map[string]string
	sets           map[string]map[string]struct{}
	hashes         map[string]map[string]float64
	boundedIndexes map[string][]string
	boundedOwners  map[string]map[string]string
}

var _ rtrec.RedisPipelineClient = (*FakeRedis)(nil)

func NewFakeRedis() *FakeRedis {
	return &FakeRedis{
		strings:        map[string]string{},
		sets:           map[string]map[string]struct{}{},
		hashes:         map[string]map[string]float64{},
		boundedIndexes: map[string][]string{},
		boundedOwners:  map[string]map[string]string{},
	}
}

func (f *FakeRedis) Get(_ context.Context, key string) (string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	if value, ok := f.strings[key]; ok {
		return value, nil
	}
	return "", fmt.Errorf("key not found: %s", key)
}

func (f *FakeRedis) HasKey(_ context.Context, key string) (bool, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	_, found := f.strings[key]
	return found, nil
}

func (f *FakeRedis) Set(_ context.Context, key, value string, _ time.Duration) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.strings[key] = value
	return nil
}

func (f *FakeRedis) SetNX(_ context.Context, key, value string, _ time.Duration) (bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.strings[key]; exists {
		return false, nil
	}
	f.strings[key] = value
	return true, nil
}

func (f *FakeRedis) CreateBoundedImmutableRecordAtomic(
	_ context.Context,
	request boundedrecord.Request,
) (boundedrecord.Result, error) {
	if err := request.Validate(); err != nil {
		return boundedrecord.Result{}, err
	}
	f.mu.Lock()
	defer f.mu.Unlock()

	index := f.boundedIndexes[request.ShardIndexKey]
	if winner, exists := f.strings[request.RecordKey]; exists {
		liveRecords, liveBytes := f.boundedUsage(index)
		return boundedrecord.Result{
			Winner:        winner,
			UsageMeasured: true,
			LiveRecords:   liveRecords,
			LiveBytes:     liveBytes,
		}, nil
	}
	owners := f.boundedOwners[request.ShardIndexKey]
	if owners == nil {
		owners = map[string]string{}
		f.boundedOwners[request.ShardIndexKey] = owners
	}
	ownerKeys := make([]string, 0, len(index))
	for _, key := range index {
		if owners[key] == request.OwnerDigest {
			ownerKeys = append(ownerKeys, key)
		}
	}
	ownerEvictionCount := len(ownerKeys) -
		request.Policy.MaximumLiveRecordsPerOwner + 1
	if ownerEvictionCount < 0 {
		ownerEvictionCount = 0
	}
	ownerVictims := ownerKeys[:ownerEvictionCount]

	liveRecords, liveBytes := f.boundedUsage(index)
	var ownerEvictionBytes int64
	for _, key := range ownerVictims {
		ownerEvictionBytes += int64(len(f.strings[key]))
	}
	projectedRecords := liveRecords - int64(len(ownerVictims)) + 1
	projectedBytes := liveBytes - ownerEvictionBytes +
		int64(len(request.Value))
	if projectedRecords > int64(request.Policy.MaximumLiveRecordsPerShard) {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   liveRecords,
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardKeyQuota
	}
	if projectedBytes > request.Policy.MaximumLiveBytesPerShard {
		return boundedrecord.Result{
			UsageMeasured: true,
			LiveRecords:   liveRecords,
			LiveBytes:     liveBytes,
		}, boundedrecord.ErrShardByteQuota
	}
	for _, victim := range ownerVictims {
		delete(f.strings, victim)
		delete(owners, victim)
		for position, key := range index {
			if key == victim {
				index = append(index[:position], index[position+1:]...)
				break
			}
		}
	}
	f.strings[request.RecordKey] = request.Value
	owners[request.RecordKey] = request.OwnerDigest
	index = append(index, request.RecordKey)
	f.boundedIndexes[request.ShardIndexKey] = index
	return boundedrecord.Result{
		Created:       true,
		OwnerEvicted:  int64(len(ownerVictims)),
		UsageMeasured: true,
		LiveRecords:   projectedRecords,
		LiveBytes:     projectedBytes,
	}, nil
}

func (f *FakeRedis) boundedUsage(index []string) (int64, int64) {
	var liveBytes int64
	for _, key := range index {
		liveBytes += int64(len(f.strings[key]))
	}
	return int64(len(index)), liveBytes
}

func (f *FakeRedis) Del(_ context.Context, keys ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, key := range keys {
		delete(f.strings, key)
		delete(f.sets, key)
		delete(f.hashes, key)
		for indexKey, index := range f.boundedIndexes {
			for position, indexedKey := range index {
				if indexedKey != key {
					continue
				}
				f.boundedIndexes[indexKey] = append(
					index[:position],
					index[position+1:]...,
				)
				delete(f.boundedOwners[indexKey], key)
				break
			}
		}
	}
	return nil
}

func (f *FakeRedis) SAdd(_ context.Context, key string, members ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.sets[key]; !exists {
		f.sets[key] = map[string]struct{}{}
	}
	for _, member := range members {
		f.sets[key][member] = struct{}{}
	}
	return nil
}

func (f *FakeRedis) SRem(_ context.Context, key string, members ...string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	set := f.sets[key]
	for _, member := range members {
		delete(set, member)
	}
	if len(set) == 0 {
		delete(f.sets, key)
	}
	return nil
}

func (f *FakeRedis) SMembers(_ context.Context, key string) ([]string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	out := make([]string, 0, len(f.sets[key]))
	for member := range f.sets[key] {
		out = append(out, member)
	}
	return out, nil
}

func (f *FakeRedis) SIsMember(_ context.Context, key, member string) (bool, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	_, exists := f.sets[key][member]
	return exists, nil
}

func (f *FakeRedis) HIncrByFloat(_ context.Context, key, field string, increment float64) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if _, exists := f.hashes[key]; !exists {
		f.hashes[key] = map[string]float64{}
	}
	f.hashes[key][field] += increment
	return nil
}

func (f *FakeRedis) HGetAll(_ context.Context, key string) (map[string]string, error) {
	f.mu.RLock()
	defer f.mu.RUnlock()
	out := make(map[string]string, len(f.hashes[key]))
	for field, value := range f.hashes[key] {
		out[field] = fmt.Sprintf("%f", value)
	}
	return out, nil
}

func (f *FakeRedis) PipelineRead(
	_ context.Context,
	operations []rtrec.PipelineOp,
) error {
	f.mu.RLock()
	defer f.mu.RUnlock()
	for index := range operations {
		operation := &operations[index]
		switch operation.Type {
		case rtrec.PipelineHGetAll:
			operation.Hash = make(map[string]string, len(f.hashes[operation.Key]))
			for field, value := range f.hashes[operation.Key] {
				operation.Hash[field] = fmt.Sprintf("%f", value)
			}
		case rtrec.PipelineSMembers:
			operation.Set = make([]string, 0, len(f.sets[operation.Key]))
			for member := range f.sets[operation.Key] {
				operation.Set = append(operation.Set, member)
			}
		case rtrec.PipelineSIsMember:
			_, operation.Bool = f.sets[operation.Key][operation.Member]
		default:
			return fmt.Errorf(
				"unsupported recommendation pipeline operation: %d",
				operation.Type,
			)
		}
	}
	return nil
}

func (f *FakeRedis) Expire(_ context.Context, _ string, _ time.Duration) error { return nil }

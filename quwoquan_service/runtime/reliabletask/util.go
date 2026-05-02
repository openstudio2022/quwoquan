package reliabletask

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"hash/fnv"
	"sort"
	"strings"
	"time"
)

const DefaultShardCount = 64

func newID(prefix string) string {
	var b [12]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
	}
	return prefix + "-" + hex.EncodeToString(b[:])
}

func clonePayload(payload map[string]string) map[string]string {
	if len(payload) == 0 {
		return map[string]string{}
	}
	out := make(map[string]string, len(payload))
	for key, value := range payload {
		out[key] = value
	}
	return out
}

func mergePayload(existing, incoming map[string]string) map[string]string {
	out := clonePayload(existing)
	for key, value := range incoming {
		if strings.TrimSpace(value) == "" {
			continue
		}
		if prev := strings.TrimSpace(out[key]); prev != "" && prev != value {
			if isCSVKey(key) {
				out[key] = mergeCSV(prev, value)
				continue
			}
		}
		out[key] = value
	}
	return out
}

func validatePayloadAllowlist(payload map[string]string, allow []string) error {
	if len(allow) == 0 {
		return nil
	}
	allowed := make(map[string]struct{}, len(allow))
	for _, key := range allow {
		allowed[strings.TrimSpace(key)] = struct{}{}
	}
	for key := range payload {
		if _, ok := allowed[key]; !ok {
			return ErrPayloadNotAllowed
		}
	}
	return nil
}

func normalizeStartAt(req DeclareTaskRequest, now time.Time) (time.Time, time.Time) {
	startAt := req.StartAt
	if startAt.IsZero() {
		startAt = now
	}
	maxDelayUntil := req.MaxDelayUntil
	if maxDelayUntil.IsZero() && req.MergeWindow > 0 {
		maxDelayUntil = startAt.Add(req.MergeWindow)
	}
	if !maxDelayUntil.IsZero() && startAt.After(maxDelayUntil) {
		startAt = maxDelayUntil
	}
	return startAt.UTC(), maxDelayUntil.UTC()
}

func extendStartAt(existing TaskOutboxRecord, req DeclareTaskRequest, now time.Time) time.Time {
	next, maxDelayUntil := normalizeStartAt(req, now)
	if existing.MaxDelayUntil.IsZero() && !maxDelayUntil.IsZero() {
		existing.MaxDelayUntil = maxDelayUntil
	}
	if !existing.MaxDelayUntil.IsZero() && next.After(existing.MaxDelayUntil) {
		next = existing.MaxDelayUntil
	}
	if next.Before(existing.StartAt) {
		return existing.StartAt
	}
	return next
}

func contains(value string, candidates []string) bool {
	if len(candidates) == 0 {
		return true
	}
	for _, candidate := range candidates {
		if strings.TrimSpace(candidate) == value {
			return true
		}
	}
	return false
}

func isCSVKey(key string) bool {
	lower := strings.ToLower(strings.TrimSpace(key))
	return strings.HasSuffix(lower, "ids") || strings.HasSuffix(lower, "triggers")
}

func mergeCSV(a, b string) string {
	seen := map[string]struct{}{}
	values := make([]string, 0)
	for _, raw := range strings.Split(a+","+b, ",") {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		values = append(values, value)
	}
	sort.Strings(values)
	return strings.Join(values, ",")
}

func shardIDForKey(key string, shardCount int) int {
	if shardCount <= 0 {
		shardCount = DefaultShardCount
	}
	trimmed := strings.TrimSpace(key)
	if trimmed == "" {
		trimmed = "default"
	}
	h := fnv.New32a()
	_, _ = h.Write([]byte(trimmed))
	return int(h.Sum32() % uint32(shardCount))
}

func shardIDForRequest(req DeclareTaskRequest) int {
	if req.ShardID > 0 {
		return req.ShardID
	}
	if req.PartitionKey != "" {
		return shardIDForKey(req.PartitionKey, DefaultShardCount)
	}
	if req.AggregateID != "" {
		return shardIDForKey(req.AggregateID, DefaultShardCount)
	}
	return 0
}

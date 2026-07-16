package reliabletask

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"hash/fnv"
	"sort"
	"strconv"
	"strings"
	"time"
)

const DefaultShardCount = 64

// NewRecordID 为可靠任务机制生成带前缀的记录标识。
func NewRecordID(prefix string) string {
	var b [12]byte
	if _, err := rand.Read(b[:]); err != nil {
		return fmt.Sprintf("%s-%d", prefix, time.Now().UnixNano())
	}
	return prefix + "-" + hex.EncodeToString(b[:])
}

// CloneStringMap 复制字符串映射，避免存储实现共享可变 payload。
func CloneStringMap(payload map[string]string) map[string]string {
	if len(payload) == 0 {
		return map[string]string{}
	}
	out := make(map[string]string, len(payload))
	for key, value := range payload {
		out[key] = value
	}
	return out
}

// MergeTaskPayload 按可靠任务合并规则合并 payload。
func MergeTaskPayload(existing, incoming map[string]string) map[string]string {
	out := CloneStringMap(existing)
	for key, value := range incoming {
		if strings.TrimSpace(value) == "" {
			continue
		}
		if prev := strings.TrimSpace(out[key]); prev != "" && prev != value {
			if isCSVKey(key) {
				out[key] = MergeCSVValues(prev, value)
				continue
			}
		}
		out[key] = value
	}
	return out
}

// ValidatePayloadAllowlist 校验 payload 是否只包含任务目录允许的字段。
func ValidatePayloadAllowlist(payload map[string]string, allow []string) error {
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

// ResolveTaskSchedule 解析任务起始时间与最大延迟上限。
func ResolveTaskSchedule(req DeclareTaskRequest, now time.Time) (time.Time, time.Time) {
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

// ExtendTaskStartAt 按 pending 合并规则顺延任务，但不越过最大延迟上限。
func ExtendTaskStartAt(existing TaskOutboxRecord, req DeclareTaskRequest, now time.Time) time.Time {
	next, maxDelayUntil := ResolveTaskSchedule(req, now)
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

// MergeCSVValues 合并、去重并稳定排序逗号分隔值。
func MergeCSVValues(a, b string) string {
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

// ResolveTaskShardID 根据显式 shard、partition key 或 aggregate id 解析分片。
func ResolveTaskShardID(req DeclareTaskRequest) int {
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

// DedupeStrings 清理、去重并稳定排序字符串集合。
func DedupeStrings(values []string) []string {
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	sort.Strings(out)
	return out
}

// DeliveryLedgerID 返回通知与接收者组合的账本标识。
func DeliveryLedgerID(notificationID string, recipientID string) string {
	return strings.TrimSpace(notificationID) + ":" + strings.TrimSpace(recipientID)
}

// ShardLeaseID 返回环境、领域、模块和分片组合的租约标识。
func ShardLeaseID(env string, domain string, module string, shardID int) string {
	return strings.TrimSpace(env) + ":" + strings.TrimSpace(domain) + ":" + strings.TrimSpace(module) + ":" + strconv.Itoa(shardID)
}

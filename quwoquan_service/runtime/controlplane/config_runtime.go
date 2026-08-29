package controlplane

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"strings"
)

type ConfigResolutionScope struct {
	Environment string `json:"environment"`
	Cluster     string `json:"cluster,omitempty"`
	Service     string `json:"service,omitempty"`
}

type ResolvedConfigValue struct {
	Key         string         `json:"key"`
	Value       any            `json:"value"`
	ScopeLevel  string         `json:"scopeLevel"`
	ScopeID     string         `json:"scopeId"`
	SourceLayer string         `json:"sourceLayer"`
	Metadata    map[string]any `json:"metadata,omitempty"`
}

type ConfigDriftSummary struct {
	InSyncInstances    int `json:"inSyncInstances"`
	OutOfSyncInstances int `json:"outOfSyncInstances"`
	// StaleInstances 统计上报新鲜度超过失联阈值的实例：它们的 inSync 声明
	// 已不可信，与 in-sync/out-of-sync 互斥计数。
	StaleInstances int `json:"staleInstances"`
	TotalInstances int `json:"totalInstances"`
}

func EffectiveConfigHash(items []ResolvedConfigValue) string {
	normalized := make([]map[string]any, 0, len(items))
	for _, item := range items {
		normalized = append(normalized, map[string]any{
			"key":         item.Key,
			"value":       item.Value,
			"scopeLevel":  item.ScopeLevel,
			"scopeId":     item.ScopeID,
			"sourceLayer": item.SourceLayer,
		})
	}
	payload, _ := json.Marshal(normalized)
	sum := sha256.Sum256(payload)
	return hex.EncodeToString(sum[:])
}

func SummarizeConfigDrift(instanceReports []Document) ConfigDriftSummary {
	out := ConfigDriftSummary{TotalInstances: len(instanceReports)}
	for _, item := range instanceReports {
		if asBool(item["inSync"]) {
			out.InSyncInstances++
		} else {
			out.OutOfSyncInstances++
		}
	}
	return out
}

func stringifyDocumentValue(value any) string {
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return ""
	}
}

func asBool(value any) bool {
	if flag, ok := value.(bool); ok {
		return flag
	}
	return false
}

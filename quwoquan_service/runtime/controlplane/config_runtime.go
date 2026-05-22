package controlplane

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"sort"
	"strings"
)

type ConfigResolutionScope struct {
	Environment string
	Cluster     string
	Service     string
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
	TotalInstances     int `json:"totalInstances"`
}

var configLayerOrder = []string{"global", "environment", "cluster", "service"}

func ResolveEffectiveConfig(
	configLayers []Document,
	configKeys []Document,
	scope ConfigResolutionScope,
) []ResolvedConfigValue {
	keyRegistry := map[string]Document{}
	resolved := map[string]ResolvedConfigValue{}

	for _, item := range configKeys {
		key := stringifyDocumentValue(item["key"])
		if key == "" {
			continue
		}
		keyRegistry[key] = cloneDocument(item)
		if _, ok := resolved[key]; !ok {
			resolved[key] = ResolvedConfigValue{
				Key:         key,
				Value:       item["default"],
				ScopeLevel:  "global",
				ScopeID:     "all",
				SourceLayer: "config_schema",
				Metadata:    cloneMapValue(item),
			}
		}
	}

	for _, level := range configLayerOrder {
		for _, layer := range configLayers {
			layerID := stringifyDocumentValue(layer["id"])
			if stringifyDocumentValue(layer["scopeLevel"]) != level {
				continue
			}
			if !matchesScope(layer, scope) {
				continue
			}
			values, _ := layer["values"].(map[string]any)
			for key, value := range values {
				resolved[key] = ResolvedConfigValue{
					Key:         key,
					Value:       value,
					ScopeLevel:  level,
					ScopeID:     stringifyDocumentValue(layer["scopeID"]),
					SourceLayer: layerID,
					Metadata:    cloneMapValue(keyRegistry[key]),
				}
			}
		}
	}

	out := make([]ResolvedConfigValue, 0, len(resolved))
	for _, item := range resolved {
		out = append(out, item)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].Key < out[j].Key
	})
	return out
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

func matchesScope(layer Document, scope ConfigResolutionScope) bool {
	level := stringifyDocumentValue(layer["scopeLevel"])
	scopeID := stringifyDocumentValue(layer["scopeID"])
	switch level {
	case "global":
		return true
	case "environment":
		return scopeID == scope.Environment
	case "cluster":
		return scopeID == scope.Cluster
	case "service":
		return scopeID == scope.Service
	default:
		return false
	}
}

func stringifyDocumentValue(value any) string {
	switch typed := value.(type) {
	case string:
		return strings.TrimSpace(typed)
	default:
		return ""
	}
}

func cloneMapValue(doc Document) map[string]any {
	if doc == nil {
		return nil
	}
	out := map[string]any{}
	for key, value := range doc {
		out[key] = value
	}
	return out
}

func asBool(value any) bool {
	if flag, ok := value.(bool); ok {
		return flag
	}
	return false
}

package main

import (
	"regexp"
	"sort"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

func isCanonicalSHA256(value string) bool {
	return regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(strings.TrimSpace(value))
}

func filterConfigInstanceReports(reports []controlplane.Document, scope controlplane.ConfigResolutionScope) []controlplane.Document {
	out := make([]controlplane.Document, 0, len(reports))
	for _, item := range reports {
		if scope.Environment != "" && stringifyDocumentValue(item["environment"]) != scope.Environment {
			continue
		}
		if scope.Cluster != "" && stringifyDocumentValue(item["cluster"]) != scope.Cluster {
			continue
		}
		if scope.Service != "" && stringifyDocumentValue(item["service"]) != scope.Service {
			continue
		}
		out = append(out, item)
	}
	return out
}

type platformConfigInstanceDriftItem struct {
	ID            string `json:"id"`
	Environment   string `json:"environment"`
	Cluster       string `json:"cluster"`
	Service       string `json:"service"`
	InstanceID    string `json:"instanceId"`
	DesiredHash   string `json:"desiredHash,omitempty"`
	EffectiveHash string `json:"effectiveHash,omitempty"`
	Source        string `json:"source,omitempty"`
	LastError     string `json:"lastError,omitempty"`
	InSync        bool   `json:"inSync"`
}

type platformServiceDriftItem struct {
	Service            string `json:"service"`
	TotalInstances     int    `json:"totalInstances"`
	InSyncInstances    int    `json:"inSyncInstances"`
	OutOfSyncInstances int    `json:"outOfSyncInstances"`
}

func summarizeConfigDriftByService(reports []controlplane.Document) []platformServiceDriftItem {
	type aggregate struct {
		total   int
		inSync  int
		outSync int
	}
	items := map[string]*aggregate{}
	for _, item := range reports {
		service := stringifyDocumentValue(item["service"])
		if service == "" {
			service = "unknown"
		}
		agg := items[service]
		if agg == nil {
			agg = &aggregate{}
			items[service] = agg
		}
		agg.total++
		if documentBool(item["inSync"]) {
			agg.inSync++
		} else {
			agg.outSync++
		}
	}
	out := make([]platformServiceDriftItem, 0, len(items))
	for service, agg := range items {
		out = append(out, platformServiceDriftItem{
			Service:            service,
			TotalInstances:     agg.total,
			InSyncInstances:    agg.inSync,
			OutOfSyncInstances: agg.outSync,
		})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].OutOfSyncInstances == out[j].OutOfSyncInstances {
			return out[i].Service < out[j].Service
		}
		return out[i].OutOfSyncInstances > out[j].OutOfSyncInstances
	})
	return out
}

func collectOutOfSyncInstances(reports []controlplane.Document, limit int) []platformConfigInstanceDriftItem {
	out := make([]platformConfigInstanceDriftItem, 0, len(reports))
	for _, item := range reports {
		if documentBool(item["inSync"]) {
			continue
		}
		out = append(out, platformConfigInstanceDriftItem{
			ID:            stringifyDocumentValue(item["id"]),
			Environment:   stringifyDocumentValue(item["environment"]),
			Cluster:       stringifyDocumentValue(item["cluster"]),
			Service:       stringifyDocumentValue(item["service"]),
			InstanceID:    stringifyDocumentValue(item["instanceId"]),
			DesiredHash:   stringifyDocumentValue(item["desiredHash"]),
			EffectiveHash: stringifyDocumentValue(item["effectiveHash"]),
			Source:        stringifyDocumentValue(item["source"]),
			LastError:     stringifyDocumentValue(item["lastError"]),
			InSync:        documentBool(item["inSync"]),
		})
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Service == out[j].Service {
			if out[i].Cluster == out[j].Cluster {
				return out[i].InstanceID < out[j].InstanceID
			}
			return out[i].Cluster < out[j].Cluster
		}
		return out[i].Service < out[j].Service
	})
	if limit > 0 && len(out) > limit {
		return out[:limit]
	}
	return out
}

func documentBool(value any) bool {
	if flag, ok := value.(bool); ok {
		return flag
	}
	return false
}

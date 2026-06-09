package main

import (
	"encoding/json"
	"net/http"
	"sort"
	"strings"

	"quwoquan_service/runtime/controlplane"
)

type runtimeConfigSnapshotResponse struct {
	Scope         controlplane.ConfigResolutionScope `json:"scope"`
	ResolvedAt    string                             `json:"resolvedAt"`
	EffectiveHash string                             `json:"effectiveHash"`
	DesiredHash   string                             `json:"desiredHash"`
	Values        []controlplane.ResolvedConfigValue `json:"values"`
	Source        string                             `json:"source"`
	DriftSummary  controlplane.ConfigDriftSummary    `json:"driftSummary"`
}

func (s *platformService) handleResolveConfig(w http.ResponseWriter, r *http.Request) {
	scope := controlplane.ConfigResolutionScope{
		Environment: strings.TrimSpace(r.URL.Query().Get("env")),
		Cluster:     strings.TrimSpace(r.URL.Query().Get("cluster")),
		Service:     strings.TrimSpace(r.URL.Query().Get("service")),
	}
	configLayers, err := s.store.ListDocuments("config_layers")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	configKeys, err := s.store.ListDocuments("config_keys")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	values := controlplane.ResolveEffectiveConfig(configLayers, configKeys, scope)
	hash := controlplane.EffectiveConfigHash(values)
	desiredHash, err := s.lookupConfigPackageDesiredHash(scope, hash)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	filteredReports := filterConfigInstanceReports(reports, scope)
	writeJSON(w, http.StatusOK, runtimeConfigSnapshotResponse{
		Scope:         scope,
		ResolvedAt:    nowRFC3339(),
		EffectiveHash: hash,
		DesiredHash:   desiredHash,
		Values:        values,
		Source:        "control-plane",
		DriftSummary:  controlplane.SummarizeConfigDrift(filteredReports),
	})
}

func (s *platformService) handleListConfigInstanceReports(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	summary := controlplane.SummarizeConfigDrift(items)
	writeJSON(w, http.StatusOK, map[string]any{
		"items":   items,
		"summary": summary,
	})
}

func (s *platformService) handleReportConfigInstance(w http.ResponseWriter, r *http.Request) {
	instanceID := segmentBetween(r.URL.Path, "/v1/control-plane/platform/configs/instances/", ":report")
	current, _, _ := s.store.GetDocument("config_instance_reports", instanceID)
	before := cloneMap(current)
	var body map[string]any
	_ = json.NewDecoder(r.Body).Decode(&body)
	if body == nil {
		body = map[string]any{}
	}
	body["id"] = instanceID
	body["instanceId"] = instanceID
	body["updatedAt"] = nowRFC3339()
	if stringifyDocumentValue(body["desiredHash"]) == "" {
		desiredHash, err := s.lookupConfigPackageDesiredHash(controlplane.ConfigResolutionScope{
			Environment: stringifyDocumentValue(body["environment"]),
			Cluster:     stringifyDocumentValue(body["cluster"]),
			Service:     stringifyDocumentValue(body["service"]),
		}, "")
		if err == nil && desiredHash != "" {
			body["desiredHash"] = desiredHash
		}
	}
	body["inSync"] = body["desiredHash"] == body["effectiveHash"]
	if err := s.store.PutDocument("config_instance_reports", instanceID, body); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	_ = s.appendAudit("config_instance_report", instanceID, "config_instance_reported", before, body, r)
	writeJSON(w, http.StatusOK, body)
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

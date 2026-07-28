package main

import (
	"encoding/json"
	"net/http"
	"regexp"
	"sort"
	"strings"

	configreportgenerated "quwoquan_service/control-plane/platform-ops/generated/platform_ops/config_instance_report"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
)

func (s *platformService) handleListConfigInstanceReports(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportStorageFailed(err.Error()))
		return
	}
	summary := controlplane.SummarizeConfigDrift(items)
	writeJSON(w, http.StatusOK, map[string]any{
		"items":   items,
		"summary": summary,
	})
}

func (s *platformService) handleReportConfigInstance(w http.ResponseWriter, r *http.Request) {
	instanceID := segmentBetween(r.URL.Path, "/control-plane/platform/configs/instances/", ":report")
	principal, hasPrincipal := rtauth.PrincipalFromContext(r.Context())
	if !hasPrincipal {
		writeControlPlaneUnauthorized(w, r, "config instance report requires a verified service principal")
		return
	}
	current, _, _ := s.store.GetDocument("config_instance_reports", instanceID)
	before := cloneMap(current)
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("decode report: "+err.Error()))
		return
	}
	if body == nil {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("config instance report body is required"))
		return
	}
	reportedService := strings.TrimSpace(stringifyDocumentValue(body["service"]))
	reportedEnvironment := strings.TrimSpace(stringifyDocumentValue(body["environment"]))
	if err := validateConfigInstanceReportPrincipal(principal, instanceID, reportedService, reportedEnvironment); err != nil {
		writeControlPlaneUnauthorized(w, r, err.Error())
		return
	}
	if !isCanonicalSHA256(s.releaseManifestDigest) {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportCandidateUnavailable("control-plane release manifest digest is unavailable"))
		return
	}
	reportedReleaseManifestDigest := strings.TrimSpace(stringifyDocumentValue(body["releaseManifestDigest"]))
	if reportedReleaseManifestDigest != s.releaseManifestDigest {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportConflict("reported release manifest digest differs from control-plane candidate"))
		return
	}
	body["releaseManifestDigest"] = s.releaseManifestDigest
	if strings.EqualFold(reportedEnvironment, "prod") &&
		strings.TrimSpace(stringifyDocumentValue(body["source"])) != "config-center" {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("prod config ACK must originate from config-center"))
		return
	}
	if strings.TrimSpace(stringifyDocumentValue(body["effectiveHash"])) == "" {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("effective config hash is required"))
		return
	}
	if strings.EqualFold(reportedEnvironment, "prod") &&
		strings.TrimSpace(stringifyDocumentValue(body["configVersion"])) == "" {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("prod config ACK requires config version"))
		return
	}
	body["id"] = instanceID
	body["instanceId"] = instanceID
	body["principalSubject"] = strings.TrimSpace(principal.Actor.AccountID)
	body["updatedAt"] = nowRFC3339()
	if s.configLayer != nil {
		// desiredHash 始终由控制面发布包快照回填，机器上报的 hash 只能用于
		// 交叉校验，不能伪造与 effectiveHash 相等的期望值来隐藏漂移。
		resolved, err := s.configLayer.Resolve(r.Context(), controlplane.ConfigResolutionScope{
			Environment: reportedEnvironment,
			Service:     reportedService,
		})
		if err != nil {
			writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("resolve desired hash: "+err.Error()))
			return
		}
		if resolved.DesiredHash == "" {
			writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid("resolved desired hash is required"))
			return
		}
		reportedDesiredHash := strings.TrimSpace(stringifyDocumentValue(body["desiredHash"]))
		if reportedDesiredHash != "" && reportedDesiredHash != resolved.DesiredHash {
			writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportConflict("reported desired hash differs from control-plane snapshot"))
			return
		}
		body["desiredHash"] = resolved.DesiredHash
	}
	body["inSync"] = body["desiredHash"] == body["effectiveHash"]
	if err := s.store.PutDocument("config_instance_reports", instanceID, body); err != nil {
		writeConfigInstanceReportError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportStorageFailed(err.Error()))
		return
	}
	_ = s.appendAudit("config_instance_report", instanceID, "config_instance_reported", before, body, r)
	writeJSON(w, http.StatusOK, body)
}

func writeConfigInstanceReportError(w http.ResponseWriter, r *http.Request, err *rterr.AppError) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func isCanonicalSHA256(value string) bool {
	return regexp.MustCompile(`^sha256:[0-9a-f]{64}$`).MatchString(strings.TrimSpace(value))
}

func validateConfigInstanceReportPrincipal(
	principal rtauth.Principal,
	instanceID string,
	reportedService string,
	reportedEnvironment string,
) error {
	const servicePrefix = "service:"
	subject := strings.TrimSpace(principal.Actor.AccountID)
	if !containsRole(principal.Roles, "service") || !strings.HasPrefix(subject, servicePrefix) {
		return errConfigReportIdentity("service principal is required")
	}
	identity := strings.TrimPrefix(subject, servicePrefix)
	serviceName, environment, found := strings.Cut(identity, "@")
	if !found || strings.TrimSpace(serviceName) == "" || strings.TrimSpace(environment) == "" {
		return errConfigReportIdentity("config ACK principal must bind service and environment")
	}
	if reportedService != serviceName || reportedEnvironment != environment {
		return errConfigReportIdentity("config ACK report service/environment does not match principal")
	}
	if !strings.HasPrefix(instanceID, serviceName+"-") {
		return errConfigReportIdentity("config ACK instance id is outside the service identity namespace")
	}
	return nil
}

type errConfigReportIdentity string

func (err errConfigReportIdentity) Error() string {
	return string(err)
}

func containsRole(roles []string, expected string) bool {
	for _, role := range roles {
		if strings.TrimSpace(role) == expected {
			return true
		}
	}
	return false
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

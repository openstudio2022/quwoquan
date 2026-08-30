package main

import (
	"context"
	"net/http"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
)

// handleConfigAckConvergence 是发布编排使用的非敏感 readiness 端点。它只返回
// ready/not_ready，详情仍必须经 operator-protected 实例报告接口读取，避免把
// 服务拓扑、hash 或版本泄露到匿名健康探针。
func (s *platformService) handleConfigAckConvergence(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRuntimeNotFound(w, r)
		return
	}
	if err := s.requireConfigAckConvergence(r.Context()); err != nil {
		w.Header().Set("Cache-Control", "no-store")
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not_ready"})
		return
	}
	w.Header().Set("Cache-Control", "no-store")
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

func (s *platformService) requireConfigAckConvergence(_ context.Context) error {
	requiredInstances := s.requiredConfigAckInstances()
	if len(requiredInstances) == 0 {
		return errConfigAckConvergence("required config ACK instances are not configured")
	}
	if !isCanonicalSHA256(s.releaseManifestDigest) {
		return errConfigAckConvergence("release manifest digest is unavailable")
	}
	reports, err := s.store.ListDocuments("config_instance_reports")
	if err != nil {
		return err
	}
	byInstance := make(map[string]controlplane.Document, len(reports))
	for _, report := range reports {
		byInstance[stringifyDocumentValue(report["instanceId"])] = report
	}
	now := time.Now().UTC()
	maxAge := time.Duration(s.configAckMaxAgeSecs) * time.Second
	for _, instanceID := range requiredInstances {
		report, ok := byInstance[instanceID]
		if !ok || !documentBool(report["inSync"]) {
			return errConfigAckConvergence("missing or drifting config ACK: " + instanceID)
		}
		if strings.TrimSpace(stringifyDocumentValue(report["source"])) != "config-center" ||
			strings.TrimSpace(stringifyDocumentValue(report["desiredHash"])) == "" ||
			stringifyDocumentValue(report["desiredHash"]) != stringifyDocumentValue(report["effectiveHash"]) ||
			stringifyDocumentValue(report["releaseManifestDigest"]) != s.releaseManifestDigest {
			return errConfigAckConvergence("invalid config ACK evidence: " + instanceID)
		}
		updatedAt, parseErr := time.Parse(time.RFC3339, stringifyDocumentValue(report["updatedAt"]))
		if parseErr != nil || now.Sub(updatedAt.UTC()) > maxAge {
			return errConfigAckConvergence("stale config ACK: " + instanceID)
		}
	}
	return nil
}

// requiredConfigAckInstances 归一化本次发布必须 ACK 的实例清单：去空、去重、
// 排序，使收敛判定与注入顺序无关。
func (s *platformService) requiredConfigAckInstances() []string {
	seen := make(map[string]struct{}, len(s.configAckInstances))
	out := make([]string, 0, len(s.configAckInstances))
	for _, raw := range s.configAckInstances {
		instanceID := strings.TrimSpace(raw)
		if instanceID == "" {
			continue
		}
		if _, exists := seen[instanceID]; exists {
			continue
		}
		seen[instanceID] = struct{}{}
		out = append(out, instanceID)
	}
	sort.Strings(out)
	return out
}

type errConfigAckConvergence string

func (err errConfigAckConvergence) Error() string {
	return string(err)
}

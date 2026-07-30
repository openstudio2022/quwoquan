package main

import (
	"crypto/subtle"
	"encoding/json"
	"net/http"
	"os"
	"sort"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
)

func writeControlPlaneUnauthorized(w http.ResponseWriter, r *http.Request, debugMessage string) {
	rterr.WriteHTTPError(
		w,
		rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
			"请先登录",
			debugMessage,
		),
		rterr.HTTPWriteOptionsFromRequest(r),
	)
}

// alertmanagerWebhookPayload 对齐 Alertmanager webhook_config 的推送 schema，
// 只消费分诊闭环需要的字段；fingerprint 是 Alertmanager 对 label set 的稳定标识。
type alertmanagerWebhookPayload struct {
	Version  string `json:"version"`
	GroupKey string `json:"groupKey"`
	Status   string `json:"status"`
	Alerts   []struct {
		Status      string            `json:"status"`
		Labels      map[string]string `json:"labels"`
		Annotations map[string]string `json:"annotations"`
		StartsAt    string            `json:"startsAt"`
		EndsAt      string            `json:"endsAt"`
		Fingerprint string            `json:"fingerprint"`
	} `json:"alerts"`
}

const activeAlertsNamespace = "active_alerts"

const alertIngestTokenHeader = "X-Alert-Ingest-Token"

// requireControlPlanePrincipal 是控制面对象完成 ContractGraph 登记前的迁移期
// 底线：除 Alertmanager ingest（以专用 token 认证的机器推送）外，任何控制面
// 路径都必须携带已验证 principal，禁止匿名触达。
func requireControlPlanePrincipal(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method == http.MethodPost && r.URL.Path == "/control-plane/platform/alerts/ingest" {
			expected := strings.TrimSpace(os.Getenv("ALERT_INGEST_TOKEN"))
			if expected == "" {
				writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", "ALERT_INGEST_TOKEN is not configured")
				return
			}
			provided := strings.TrimSpace(r.Header.Get(alertIngestTokenHeader))
			if subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) != 1 {
				writeControlPlaneUnauthorized(w, r, "alert ingest token mismatch")
				return
			}
			next.ServeHTTP(w, r)
			return
		}
		if _, ok := rtauth.PrincipalFromContext(r.Context()); !ok {
			writeControlPlaneUnauthorized(w, r, "verified operator principal is required")
			return
		}
		next.ServeHTTP(w, r)
	})
}

// handleIngestAlertmanagerWebhook 是 Alertmanager receiver 的回流终点：
// firing 建立/刷新活动告警，resolved 关闭；ack 状态由值班人经 :ack 显式推进。
func (s *platformService) handleIngestAlertmanagerWebhook(w http.ResponseWriter, r *http.Request) {
	var payload alertmanagerWebhookPayload
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "invalid alertmanager payload: "+err.Error())
		return
	}
	if len(payload.Alerts) == 0 {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "alertmanager payload has no alerts")
		return
	}
	ingested := 0
	for _, alert := range payload.Alerts {
		fingerprint := strings.TrimSpace(alert.Fingerprint)
		if fingerprint == "" {
			continue
		}
		current, exists, err := s.store.GetDocument(activeAlertsNamespace, fingerprint)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		status := strings.TrimSpace(alert.Status)
		if status == "" {
			status = strings.TrimSpace(payload.Status)
		}
		document := map[string]any{
			"id":          fingerprint,
			"fingerprint": fingerprint,
			"alertName":   alert.Labels["alertname"],
			"severity":    alert.Labels["severity"],
			"service":     alert.Labels["service"],
			"labels":      alert.Labels,
			"annotations": alert.Annotations,
			"startsAt":    alert.StartsAt,
			"endsAt":      alert.EndsAt,
			"groupKey":    payload.GroupKey,
			"status":      status,
			"updatedAt":   nowRFC3339(),
		}
		if exists {
			// ack 状态在同一 firing 周期内保持，resolved 后归档为 resolved。
			if ackedBy := stringifyDocumentValue(current["ackedBy"]); ackedBy != "" && status == "firing" {
				document["status"] = "acknowledged"
				document["ackedBy"] = current["ackedBy"]
				document["ackedAt"] = current["ackedAt"]
			}
		}
		if err := s.store.PutDocument(activeAlertsNamespace, fingerprint, document); err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		ingested++
	}
	if ingested == 0 {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "alertmanager alerts missing fingerprint")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ingested": ingested})
}

func (s *platformService) handleListActiveAlerts(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments(activeAlertsNamespace)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	statusFilter := strings.TrimSpace(r.URL.Query().Get("status"))
	filtered := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if statusFilter != "" && stringifyDocumentValue(item["status"]) != statusFilter {
			continue
		}
		filtered = append(filtered, item)
	}
	sort.Slice(filtered, func(i, j int) bool {
		return stringifyDocumentValue(filtered[i]["updatedAt"]) > stringifyDocumentValue(filtered[j]["updatedAt"])
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": filtered})
}

func (s *platformService) handleAckAlert(w http.ResponseWriter, r *http.Request) {
	fingerprint := segmentBetween(r.URL.Path, "/control-plane/platform/alerts/", ":ack")
	current, ok, err := s.store.GetDocument(activeAlertsNamespace, fingerprint)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "alert not found")
		return
	}
	before := cloneMap(current)
	actor := actorFromRequest(r)
	current["status"] = "acknowledged"
	current["ackedBy"] = actor
	current["ackedAt"] = nowRFC3339()
	current["updatedAt"] = nowRFC3339()
	if err := s.store.PutDocument(activeAlertsNamespace, fingerprint, current); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if err := s.appendAudit("active_alert", fingerprint, "alert_acknowledged", before, current, r); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, current)
}

func (s *platformService) countActiveAlerts() (int, error) {
	items, err := s.store.ListDocuments(activeAlertsNamespace)
	if err != nil {
		return 0, err
	}
	count := 0
	for _, item := range items {
		status := stringifyDocumentValue(item["status"])
		if status == "firing" || status == "acknowledged" {
			count++
		}
	}
	return count, nil
}

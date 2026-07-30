package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"sort"
	"strings"
	"time"

	"quwoquan_service/runtime/controlplane"
	messaging "quwoquan_service/runtime/messaging"
)

const premiumPoolNamespace = "premium_pool_entries"

const (
	premiumPoolEntryUpsertedEvent        = "PremiumPoolEntryUpserted"
	premiumPoolEntryRolledBackEvent      = "PremiumPoolEntryRolledBack"
	premiumPoolEntryTakedownEjectedEvent = "PremiumPoolEntryTakedownEjected"
)

type premiumPoolEntry struct {
	ID               string  `json:"id"`
	ContentID        string  `json:"contentId"`
	Scope            string  `json:"scope"`
	Status           string  `json:"status"`
	QualityScore     float64 `json:"qualityScore"`
	QualityAdmission string  `json:"qualityAdmission"`
	SupplySource     string  `json:"supplySource,omitempty"`
	SourceTaskID     string  `json:"sourceTaskId,omitempty"`
	AuditID          string  `json:"auditId"`
	RollbackToken    string  `json:"rollbackToken"`
	FeaturedAt       string  `json:"featuredAt"`
	ExpiresAt        string  `json:"expiresAt"`
	TakedownEjected  bool    `json:"takedownEjected"`
	UpdatedAt        string  `json:"updatedAt"`
}

type premiumPoolUpsertRequest struct {
	ContentID        string  `json:"contentId"`
	Scope            string  `json:"scope"`
	QualityScore     float64 `json:"qualityScore"`
	QualityAdmission string  `json:"qualityAdmission"`
	SupplySource     string  `json:"supplySource"`
	SourceTaskID     string  `json:"sourceTaskId"`
	AuditID          string  `json:"auditId"`
	RollbackToken    string  `json:"rollbackToken"`
	ExpiresAt        string  `json:"expiresAt"`
}

func (s *productService) handleListPremiumPool(w http.ResponseWriter, r *http.Request) {
	items, err := s.store.ListDocuments(premiumPoolNamespace)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	activeOnly := strings.EqualFold(strings.TrimSpace(r.URL.Query().Get("activeOnly")), "true")
	now := time.Now().UTC()
	out := make([]premiumPoolEntry, 0, len(items))
	for _, item := range items {
		entry, err := decodeDocument[premiumPoolEntry](item)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		if activeOnly && !entry.activeAt(now) {
			continue
		}
		out = append(out, entry)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].UpdatedAt > out[j].UpdatedAt
	})
	writeJSON(w, http.StatusOK, map[string]any{"items": out})
}

func (s *productService) handleUpsertPremiumPool(w http.ResponseWriter, r *http.Request) {
	var body premiumPoolUpsertRequest
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "invalid json body")
		return
	}
	entry, err := buildPremiumPoolEntry(body, time.Now().UTC())
	if err != nil {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", err.Error())
		return
	}
	before, _, err := s.store.GetDocument(premiumPoolNamespace, entry.ID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if err := s.putDocument(premiumPoolNamespace, entry.ID, entry); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if err := s.publishPremiumPoolEvent(r, premiumPoolEntryUpsertedEvent, entry); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := premiumPoolWorkflow(entry, "featured")
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       entry.AuditID,
		ObjectType:    "premium_pool_entry",
		ObjectID:      entry.ID,
		Action:        "feature_global_premium",
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: entry.RollbackToken,
		Before:        before,
		After:         documentFromStruct(entry),
		Metadata: map[string]any{
			"scope":            entry.Scope,
			"qualityAdmission": entry.QualityAdmission,
			"qualityScore":     entry.QualityScore,
		},
	})
	writeJSON(w, http.StatusOK, entry)
}

func (s *productService) handleRollbackPremiumPool(w http.ResponseWriter, r *http.Request) {
	contentID := segmentBetween(r.URL.Path, "/control-plane/product/recommendation/premium-pool/", ":rollback")
	s.transitionPremiumPoolEntry(w, r, contentID, "rolled_back", "rollback_global_premium", false)
}

// handleTakedownPremiumPool 是高危处置（把内容从全局精选池弹出并广播事件），
// 必须由两个不同 principal 对同一 payload digest 双签后才执行。
func (s *productService) handleTakedownPremiumPool(w http.ResponseWriter, r *http.Request) {
	contentID := segmentBetween(r.URL.Path, "/control-plane/product/recommendation/premium-pool/", ":takedown")
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeRuntimeError(w, r, http.StatusBadRequest, "请求处理失败", "Idempotency-Key is required")
		return
	}
	id := premiumPoolEntryID(contentID)
	entry, ok, err := s.getPremiumPoolEntry(id)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "premium pool entry not found")
		return
	}
	actor := actorFromRequest(r)
	payloadDigest := dualApprovalPayloadDigest(documentFromStruct(entry), "takedown")
	approvals, err := s.store.ListApprovals("premium_pool_entry", entry.ID)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !approvalExistsForIntent(approvals, actor, payloadDigest, "takedown") {
		if err := s.store.AppendApproval(controlplane.ApprovalDecision{
			ObjectType:    "premium_pool_entry",
			ObjectID:      entry.ID,
			Mode:          "dual",
			Actor:         actor,
			Decision:      "takedown",
			PayloadDigest: payloadDigest,
		}); err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
		approvals, err = s.store.ListApprovals("premium_pool_entry", entry.ID)
		if err != nil {
			writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
			return
		}
	}
	if !dualApprovalSatisfied(approvals, payloadDigest, "takedown") {
		writeJSON(w, http.StatusOK, map[string]any{
			"entry":          entry,
			"approvalCount":  countMatchingApprovals(approvals, payloadDigest, "takedown"),
			"pending":        true,
			"approvalState":  "pending_second_principal",
			"payloadDigest":  payloadDigest,
			"approverActors": distinctMatchingApprovalActors(approvals, payloadDigest, "takedown"),
		})
		return
	}
	before := documentFromStruct(entry)
	entry.Status = "takedown_ejected"
	entry.TakedownEjected = true
	entry.UpdatedAt = nowRFC3339()
	workflow := premiumPoolWorkflow(entry, entry.Status)
	atomicStore, ok := s.store.(controlplane.AtomicMutationStore)
	if !ok {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", "atomic mutation store is required")
		return
	}
	receipt, err := atomicStore.CommitApprovedMutation(controlplane.ApprovedMutation{
		Namespace:        premiumPoolNamespace,
		ObjectType:       "premium_pool_entry",
		ObjectID:         entry.ID,
		Intent:           "takedown",
		ApprovalDecision: "takedown",
		PayloadDigest:    payloadDigest,
		IdempotencyKey:   idempotencyKey,
		Document:         documentFromStruct(entry),
		Workflow:         workflow,
		Audit: controlplane.AuditEvent{
			AuditID:       "takedown_eject_global_premium_" + entry.ID + "_" + payloadDigest[:12],
			ObjectType:    "premium_pool_entry",
			ObjectID:      entry.ID,
			Action:        "takedown_eject_global_premium",
			DangerLevel:   "critical",
			Actor:         actor,
			Environment:   environmentFromRequest(r),
			RequestID:     requestIDFromRequest(r),
			TraceID:       traceIDFromRequest(r),
			WorkflowRef:   workflow.WorkflowID,
			RollbackToken: entry.RollbackToken,
			Before:        before,
			After:         documentFromStruct(entry),
		},
		OutboxEvents: []controlplane.MutationOutboxEvent{{
			EventID:       "premium_pool_takedown_" + payloadDigest[:32],
			EventType:     premiumPoolEntryTakedownEjectedEvent,
			AggregateType: "PremiumPoolEntry",
			AggregateID:   entry.ID,
			Payload:       documentFromStruct(entry),
			OccurredAt:    entry.UpdatedAt,
		}},
	})
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, controlplane.ErrMutationIdempotencyConflict) ||
			errors.Is(err, controlplane.ErrDualApprovalRequired) {
			status = http.StatusConflict
		}
		writeRuntimeError(w, r, status, "请求处理失败", err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"entry":   entry,
		"pending": false,
		"receipt": receipt,
	})
}

func (s *productService) transitionPremiumPoolEntry(w http.ResponseWriter, r *http.Request, contentID, status, action string, takedown bool) {
	id := premiumPoolEntryID(contentID)
	entry, ok, err := s.getPremiumPoolEntry(id)
	if err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	if !ok {
		writeRuntimeError(w, r, http.StatusNotFound, "请求处理失败", "premium pool entry not found")
		return
	}
	before := documentFromStruct(entry)
	entry.Status = status
	entry.TakedownEjected = takedown
	entry.UpdatedAt = nowRFC3339()
	if err := s.putDocument(premiumPoolNamespace, entry.ID, entry); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	eventType := premiumPoolEntryRolledBackEvent
	if takedown {
		eventType = premiumPoolEntryTakedownEjectedEvent
	}
	if err := s.publishPremiumPoolEvent(r, eventType, entry); err != nil {
		writeRuntimeError(w, r, http.StatusInternalServerError, "请求处理失败", err.Error())
		return
	}
	workflow := premiumPoolWorkflow(entry, status)
	_ = s.store.UpsertWorkflow(workflow)
	_ = s.store.AppendAudit(controlplane.AuditEvent{
		AuditID:       action + "_" + entry.ID,
		ObjectType:    "premium_pool_entry",
		ObjectID:      entry.ID,
		Action:        action,
		DangerLevel:   "high",
		Actor:         actorFromRequest(r),
		Environment:   environmentFromRequest(r),
		RequestID:     requestIDFromRequest(r),
		TraceID:       traceIDFromRequest(r),
		WorkflowRef:   workflow.WorkflowID,
		RollbackToken: entry.RollbackToken,
		Before:        before,
		After:         documentFromStruct(entry),
	})
	writeJSON(w, http.StatusOK, entry)
}

func (s *productService) getPremiumPoolEntry(id string) (premiumPoolEntry, bool, error) {
	doc, ok, err := s.store.GetDocument(premiumPoolNamespace, id)
	if err != nil || !ok {
		return premiumPoolEntry{}, ok, err
	}
	entry, err := decodeDocument[premiumPoolEntry](doc)
	return entry, true, err
}

func (s *productService) publishPremiumPoolEvent(r *http.Request, eventType string, entry premiumPoolEntry) error {
	if s == nil || s.publisher == nil {
		return nil
	}
	occurredAt := strings.TrimSpace(entry.UpdatedAt)
	if occurredAt == "" {
		occurredAt = nowRFC3339()
	}
	return s.publisher.Publish(r.Context(), messaging.DomainEvent{
		Type:          eventType,
		AggregateType: "PremiumPoolEntry",
		AggregateID:   entry.ID,
		Payload:       documentFromStruct(entry),
		OccurredAt:    occurredAt,
	})
}

func buildPremiumPoolEntry(body premiumPoolUpsertRequest, now time.Time) (premiumPoolEntry, error) {
	contentID := strings.TrimSpace(body.ContentID)
	if contentID == "" {
		return premiumPoolEntry{}, errString("contentId is required")
	}
	scope := strings.TrimSpace(strings.ToLower(body.Scope))
	if scope == "" {
		scope = "global"
	}
	if scope != "global" {
		return premiumPoolEntry{}, errString("premium pool scope must be global")
	}
	admission := strings.TrimSpace(strings.ToLower(body.QualityAdmission))
	if admission != "approved" {
		return premiumPoolEntry{}, errString("qualityAdmission must be approved")
	}
	if body.QualityScore < 0.75 {
		return premiumPoolEntry{}, errString("qualityScore must be >= 0.75")
	}
	auditID := strings.TrimSpace(body.AuditID)
	if auditID == "" {
		return premiumPoolEntry{}, errString("auditId is required")
	}
	expiresAt := strings.TrimSpace(body.ExpiresAt)
	if expiresAt == "" {
		return premiumPoolEntry{}, errString("expiresAt is required")
	}
	exp, err := time.Parse(time.RFC3339, expiresAt)
	if err != nil {
		return premiumPoolEntry{}, errString("expiresAt must be RFC3339")
	}
	if !exp.After(now) {
		return premiumPoolEntry{}, errString("expiresAt must be in the future")
	}
	rollbackToken := strings.TrimSpace(body.RollbackToken)
	if rollbackToken == "" {
		rollbackToken = "rbk-premium-" + contentID
	}
	return premiumPoolEntry{
		ID:               premiumPoolEntryID(contentID),
		ContentID:        contentID,
		Scope:            scope,
		Status:           "active",
		QualityScore:     body.QualityScore,
		QualityAdmission: admission,
		SupplySource:     strings.TrimSpace(body.SupplySource),
		SourceTaskID:     strings.TrimSpace(body.SourceTaskID),
		AuditID:          auditID,
		RollbackToken:    rollbackToken,
		FeaturedAt:       now.Format(time.RFC3339),
		ExpiresAt:        exp.UTC().Format(time.RFC3339),
		UpdatedAt:        now.Format(time.RFC3339),
	}, nil
}

func premiumPoolEntryID(contentID string) string {
	return strings.TrimSpace(contentID)
}

func (e premiumPoolEntry) activeAt(now time.Time) bool {
	if e.Status != "active" || e.TakedownEjected {
		return false
	}
	exp, err := time.Parse(time.RFC3339, e.ExpiresAt)
	if err != nil {
		return false
	}
	return exp.After(now)
}

func premiumPoolWorkflow(entry premiumPoolEntry, state string) controlplane.WorkflowState {
	return controlplane.WorkflowState{
		ObjectType: "premium_pool_entry",
		ObjectID:   entry.ID,
		WorkflowID: "global_premium_pool:" + entry.ID,
		State:      state,
		History: []controlplane.WorkflowTransition{{
			From:   "",
			To:     state,
			Action: state,
			Actor:  "product-ops",
			At:     nowRFC3339(),
		}},
		UpdatedAt: nowRFC3339(),
	}
}

type errString string

func (e errString) Error() string { return string(e) }

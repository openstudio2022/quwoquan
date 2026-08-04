// spec_ref: specs/feature-tree/product-ops-growth/event-ingestion-and-analytics/event-schema-governance/spec.md#gwt-001
package visit_record_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	visithttp "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/adapters/inbound/http"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

func TestVisitServiceOwnsValidationAndImmutableReplay(t *testing.T) {
	store := newLocalVisitStore()
	service := visitapplication.NewService(store)
	input := visitapplication.RecordVisitCommand{
		UserID: "actor-1", TargetType: "page", TargetKey: "home",
	}
	first, err := service.RecordVisit(context.Background(), input, "command-1")
	if err != nil || first.VisitCount != 1 || first.Replayed {
		t.Fatalf("first result=%+v err=%v", first, err)
	}
	replay, err := service.RecordVisit(context.Background(), input, "command-1")
	if err != nil || replay.VisitCount != 1 || !replay.Replayed ||
		!replay.OccurredAt.Equal(first.OccurredAt) {
		t.Fatalf("replay changed first receipt: first=%+v replay=%+v err=%v", first, replay, err)
	}
	if _, err := service.RecordVisit(context.Background(), visitapplication.RecordVisitCommand{
		UserID: "actor-1", TargetType: "page", TargetKey: "other",
	}, "command-1"); !errors.Is(err, visitapplication.ErrIdempotencyConflict) {
		t.Fatalf("conflicting key error=%v", err)
	}
	if _, err := service.RecordVisit(context.Background(), input, " "); !errors.Is(err, visitapplication.ErrIdempotencyRequired) {
		t.Fatalf("missing key error=%v", err)
	}
	if _, err := service.RecordVisit(context.Background(), input, strings.Repeat("x", 257)); !errors.Is(err, visitapplication.ErrInvalidInput) {
		t.Fatalf("oversized key error=%v", err)
	}
	if _, err := service.RecordVisit(context.Background(), visitapplication.RecordVisitCommand{
		UserID: "actor-1", TargetType: "unknown", TargetKey: "home",
	}, "command-2"); !errors.Is(err, visitapplication.ErrInvalidInput) {
		t.Fatalf("unknown target type error=%v", err)
	}
	if store.visitCount("actor-1", "page", "home") != 1 || store.receiptCount() != 1 {
		t.Fatalf("local atomic store drifted: visits=%d receipts=%d",
			store.visitCount("actor-1", "page", "home"), store.receiptCount())
	}
}

func TestVisitHTTPBoundaryRejectsSpoofingAndMapsObjectErrors(t *testing.T) {
	store := newLocalVisitStore()
	handler := visithttp.NewHandler(visitapplication.NewService(store))
	mux := http.NewServeMux()
	handler.Register(mux)

	spoofed := localRequest(
		http.MethodPost,
		"/ops/visits",
		`{"targetType":"page","targetKey":"home","userId":"attacker"}`,
		"visit-local-1",
		"persona-local",
	)
	spoofedResponse := httptest.NewRecorder()
	mux.ServeHTTP(spoofedResponse, spoofed)
	assertLocalError(t, spoofedResponse, http.StatusBadRequest, "OPS.USER.visit_invalid_argument")

	missingKey := localRequest(
		http.MethodPost,
		"/ops/visits",
		`{"targetType":"page","targetKey":"home"}`,
		"",
		"persona-local",
	)
	missingResponse := httptest.NewRecorder()
	mux.ServeHTTP(missingResponse, missingKey)
	assertLocalError(t, missingResponse, http.StatusBadRequest, "OPS.USER.visit_invalid_argument")

	first := localRequest(
		http.MethodPost,
		"/ops/visits",
		`{"targetType":"page","targetKey":"home"}`,
		"visit-local-2",
		"persona-local",
	)
	firstResponse := httptest.NewRecorder()
	mux.ServeHTTP(firstResponse, first)
	if firstResponse.Code != http.StatusOK {
		t.Fatalf("first status=%d body=%s", firstResponse.Code, firstResponse.Body.String())
	}
	var firstReceipt visitapplication.RecordVisitReceipt
	if err := json.Unmarshal(firstResponse.Body.Bytes(), &firstReceipt); err != nil {
		t.Fatalf("decode RecordVisitReceipt: %v", err)
	}
	if firstReceipt.TargetType != "page" || firstReceipt.TargetKey != "home" ||
		firstReceipt.VisitCount != 1 || firstReceipt.Replayed ||
		firstReceipt.OccurredAt.IsZero() {
		t.Fatalf("unexpected RecordVisitReceipt: %+v", firstReceipt)
	}
	if bytes.Contains(firstResponse.Body.Bytes(), []byte(`"userId"`)) {
		t.Fatalf("RecordVisitReceipt leaked actor: %s", firstResponse.Body.String())
	}
	if store.lastInput.UserID == "" || store.lastInput.UserID == "persona-local" {
		t.Fatalf("adapter must persist only a namespaced irreversible actor hash: %+v", store.lastInput)
	}

	conflict := localRequest(
		http.MethodPost,
		"/ops/visits",
		`{"targetType":"page","targetKey":"other"}`,
		"visit-local-2",
		"persona-local",
	)
	conflictResponse := httptest.NewRecorder()
	mux.ServeHTTP(conflictResponse, conflict)
	assertLocalError(t, conflictResponse, http.StatusConflict, "OPS.USER.visit_idempotency_conflict")

	store.commitErr = errors.New("mongo unavailable")
	failure := localRequest(
		http.MethodPost,
		"/ops/visits",
		`{"targetType":"post","targetKey":"post-1"}`,
		"visit-local-3",
		"persona-local",
	)
	failureResponse := httptest.NewRecorder()
	mux.ServeHTTP(failureResponse, failure)
	assertLocalError(t, failureResponse, http.StatusInternalServerError, "OPS.SYSTEM.visit_storage_write_failed")
}

func localRequest(
	method string,
	path string,
	body string,
	idempotencyKey string,
	personaID string,
) *http.Request {
	request := httptest.NewRequest(method, path, bytes.NewBufferString(body))
	request.Header.Set("X-Request-Id", "visit-local-request")
	request.Header.Set("X-Trace-Id", "visit-local-trace")
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{PersonaID: personaID},
	}))
}

func assertLocalError(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
	status int,
	code string,
) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response: %v", err)
	}
	if response.Code != code {
		t.Fatalf("code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}

type localReceipt struct {
	digest string
	result visitapplication.VisitRecord
}

type localVisitStore struct {
	mu        sync.Mutex
	visits    map[string]visitapplication.VisitRecord
	receipts  map[string]localReceipt
	lastInput visitapplication.RecordVisitCommand
	commitErr error
}

func newLocalVisitStore() *localVisitStore {
	return &localVisitStore{
		visits:   map[string]visitapplication.VisitRecord{},
		receipts: map[string]localReceipt{},
	}
}

func (s *localVisitStore) CommitVisit(
	_ context.Context,
	command visitapplication.CommitCommand,
) (visitapplication.RecordVisitReceipt, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.commitErr != nil {
		return visitapplication.RecordVisitReceipt{}, s.commitErr
	}
	s.lastInput = command.Input
	if receipt, ok := s.receipts[command.ReceiptID]; ok {
		if receipt.digest != command.CommandDigest {
			return visitapplication.RecordVisitReceipt{}, visitapplication.ErrIdempotencyConflict
		}
		return visitapplication.RecordVisitReceipt{VisitRecord: receipt.result, Replayed: true}, nil
	}
	key := command.Input.UserID + ":" + command.Input.TargetType + ":" + command.Input.TargetKey
	record := s.visits[key]
	record.UserID = command.Input.UserID
	record.TargetType = command.Input.TargetType
	record.TargetKey = command.Input.TargetKey
	record.VisitCount++
	record.OccurredAt = time.Now().UTC()
	s.visits[key] = record
	s.receipts[command.ReceiptID] = localReceipt{
		digest: command.CommandDigest,
		result: record,
	}
	return visitapplication.RecordVisitReceipt{VisitRecord: record}, nil
}

func (s *localVisitStore) GetVisitStats(
	_ context.Context,
	query visitapplication.VisitStatsQuery,
) (visitapplication.VisitStats, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := visitapplication.VisitStats{Items: []visitapplication.VisitRecord{}}
	for _, item := range s.visits {
		if query.TargetType != "" && item.TargetType != query.TargetType {
			continue
		}
		if query.TargetKey != "" && item.TargetKey != query.TargetKey {
			continue
		}
		out.TotalVisits += item.VisitCount
		out.Items = append(out.Items, item)
	}
	return out, nil
}

func (s *localVisitStore) visitCount(userID, targetType, targetKey string) int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.visits[userID+":"+targetType+":"+targetKey].VisitCount
}

func (s *localVisitStore) receiptCount() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.receipts)
}

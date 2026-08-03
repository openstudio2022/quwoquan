package httpadapter

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/product-ops-service/generated/product_ops/event_record"
	eventapp "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/application"
)

const maxRequestBytes = 128 << 10

type IngestObserver func(result string, count int, duration time.Duration)
type AcceptedObserver func([]eventapp.EventRecordInput)

type Handler struct {
	service    *eventapp.TelemetryService
	onIngest   IngestObserver
	onAccepted AcceptedObserver
}

func NewHandler(service *eventapp.TelemetryService, onIngest IngestObserver, onAccepted AcceptedObserver) *Handler {
	if service == nil {
		panic("event record HTTP handler requires telemetry service")
	}
	return &Handler{service: service, onIngest: onIngest, onAccepted: onAccepted}
}

func (handler *Handler) Register(mux *http.ServeMux) {
	mux.Handle("POST /ops/events", handler)
}

func (handler *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	startedAt := time.Now()
	result := "rejected"
	eventCount := 0
	defer func() {
		if handler.onIngest != nil {
			handler.onIngest(result, eventCount, time.Since(startedAt))
		}
	}()
	if !hasVerifiedActor(r) {
		result = "unauthorized"
		writeError(w, r, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
			"请先登录",
			"verified telemetry actor is required",
		).WithMetadata("unauthorized", http.StatusUnauthorized).WithRecovery("reauth", 0))
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, maxRequestBytes+1))
	if err != nil || len(raw) == 0 || len(raw) > maxRequestBytes {
		writeError(w, r, generated.AppErrorFromEventBatchInvalid("request body exceeds telemetry limit"))
		return
	}
	canonical, err := canonicalJSON(raw)
	if err != nil {
		writeError(w, r, generated.AppErrorFromEventBatchInvalid(err.Error()))
		return
	}
	digest := sha256.Sum256(canonical)
	batchKey := hex.EncodeToString(digest[:])
	if !strings.EqualFold(strings.TrimSpace(r.Header.Get("Idempotency-Key")), batchKey) {
		writeError(w, r, generated.AppErrorFromIdempotencyKeyInvalid("idempotency digest mismatch"))
		return
	}
	var body struct {
		Events []eventapp.EventRecordInput `json:"events"`
	}
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&body); err != nil {
		writeError(w, r, generated.AppErrorFromEventBatchInvalid(err.Error()))
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeError(w, r, generated.AppErrorFromEventBatchInvalid("request body must contain exactly one JSON object"))
		return
	}
	eventCount = len(body.Events)
	ack, err := handler.service.ReportEventBatch(r.Context(), batchKey, body.Events)
	if err != nil {
		switch {
		case errors.Is(err, eventapp.ErrInvalidEventBatch):
			result = "invalid"
			writeError(w, r, generated.AppErrorFromEventBatchInvalid(err.Error()))
		default:
			result = "unavailable"
			writeError(w, r, generated.AppErrorFromLogstoreUnavailable(err.Error()))
		}
		return
	}
	if ack.DuplicateBatch {
		result = "duplicate"
	} else {
		result = "accepted"
		if handler.onAccepted != nil {
			handler.onAccepted(body.Events)
		}
	}
	writeJSON(w, http.StatusOK, ack)
}

func hasVerifiedActor(r *http.Request) bool {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return false
	}
	actorID, ok := principal.Actor.BusinessActorID()
	return ok && strings.TrimSpace(actorID) != ""
}

func canonicalJSON(raw []byte) ([]byte, error) {
	var value any
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return nil, err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return nil, errors.New("request body must contain exactly one JSON value")
	}
	return json.Marshal(value)
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

package http

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterrors "quwoquan_service/runtime/errors"
	feedbackapplication "quwoquan_service/services/search-service/internal/search/feedback_fact/application"
)

const (
	reportFeedbackOperation = "search.feedback_fact.ReportSearchFeedback"
	maxRequestBodyBytes     = 64 << 10
)

var moduleSearch = rterrors.Module("SEARCH")

type Handler struct {
	service  *feedbackapplication.Service
	observer feedbackapplication.Observer
}

func NewHandler(
	service *feedbackapplication.Service,
	observer feedbackapplication.Observer,
) *Handler {
	return &Handler{service: service, observer: observer}
}

func (h *Handler) Routes() http.Handler {
	mux := http.NewServeMux()
	h.Register(mux)
	return mux
}

func (h *Handler) Register(mux *http.ServeMux) {
	mux.HandleFunc(operationPattern(), h.handleFeedback)
}

func operationPattern() string {
	for _, descriptor := range operationsecurity.ForDomain("search") {
		if descriptor.CanonicalOperationID != reportFeedbackOperation {
			continue
		}
		method := strings.TrimSpace(descriptor.Method)
		path := strings.TrimSpace(descriptor.PathTemplate)
		if method != "" && path != "" {
			return method + " " + path
		}
		break
	}
	panic(fmt.Sprintf(
		"generated search operation route missing: %s",
		reportFeedbackOperation,
	))
}

func (h *Handler) handleFeedback(w http.ResponseWriter, r *http.Request) {
	requestID := requestIDFrom(r)
	r.Body = http.MaxBytesReader(w, r.Body, maxRequestBodyBytes)
	var event feedbackapplication.Event
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&event); err != nil {
		writeErr(
			w,
			requestID,
			rterrors.NewInvalidArgument(
				moduleSearch,
				"反馈格式不正确。",
				"decode feedback body: "+err.Error(),
			),
		)
		return
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		writeErr(
			w,
			requestID,
			rterrors.NewInvalidArgument(
				moduleSearch,
				"反馈格式不正确。",
				"feedback body must contain exactly one JSON object",
			),
		)
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" || len(idempotencyKey) > 200 {
		writeErr(
			w,
			requestID,
			rterrors.NewInvalidArgument(
				moduleSearch,
				"反馈缺少有效的幂等标识。",
				"Idempotency-Key is required and must be at most 200 characters",
			),
		)
		return
	}
	canonicalPayload, err := json.Marshal(event)
	if err != nil {
		writeStorageError(
			w,
			requestID,
			fmt.Errorf("marshal canonical feedback: %w", err),
		)
		return
	}
	event.ViewerID = actorIDFrom(r)
	err = h.service.Report(r.Context(), event, feedbackapplication.CommandMeta{
		IdempotencyKey: idempotencyKey,
		CommandDigest:  fmt.Sprintf("%x", sha256.Sum256(canonicalPayload)),
	})
	if err != nil {
		switch {
		case errors.Is(err, feedbackapplication.ErrInvalid):
			writeErr(
				w,
				requestID,
				rterrors.NewInvalidArgument(
					moduleSearch,
					"反馈格式不正确。",
					err.Error(),
				),
			)
		case errors.Is(err, feedbackapplication.ErrIdempotencyConflict):
			writeErr(
				w,
				requestID,
				rterrors.NewAppError(
					rterrors.NewCode(
						moduleSearch,
						rterrors.KindUser,
						"feedback_conflict",
					),
					"该搜索反馈与已记录请求冲突。",
					err.Error(),
				).WithMetadata("feedback_conflict", http.StatusConflict).
					WithRecoveryDirective("surface", "inlineCard", 0),
			)
		default:
			writeStorageError(w, requestID, err)
		}
		return
	}
	if h.observer != nil {
		h.observer.ObserveFeedback(event.EventType)
	}
	writeJSON(
		w,
		http.StatusAccepted,
		map[string]any{"accepted": true, "requestId": requestID},
	)
}

func actorIDFrom(r *http.Request) string {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return ""
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return personaID
	}
	return strings.TrimSpace(principal.Actor.DeviceActorID)
}

func requestIDFrom(r *http.Request) string {
	if requestID := strings.TrimSpace(r.Header.Get("X-Request-Id")); requestID != "" {
		return requestID
	}
	return fmt.Sprintf("search.req.%d", time.Now().UnixNano())
}

func writeStorageError(
	w http.ResponseWriter,
	requestID string,
	err error,
) {
	writeErr(
		w,
		requestID,
		rterrors.NewAppError(
			rterrors.NewCode(
				moduleSearch,
				rterrors.KindSystem,
				"storage_write_failed",
			),
			"反馈暂时无法记录，请稍后重试。",
			err.Error(),
		).WithMetadata("storage_write_failed", http.StatusInternalServerError).
			WithRecoveryDirective("retry", "snackbar", 5),
	)
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeErr(w http.ResponseWriter, requestID string, err error) {
	rterrors.WriteHTTPError(
		w,
		err,
		rterrors.HTTPWriteOptions{RequestID: requestID},
	)
}

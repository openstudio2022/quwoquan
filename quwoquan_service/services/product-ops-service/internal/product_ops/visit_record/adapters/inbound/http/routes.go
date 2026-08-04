// Package httpadapter owns the complete VisitRecord HTTP boundary: trusted
// actor derivation, strict decoding, wire encoding, application error mapping,
// and route/method rejection.
package httpadapter

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	visitgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/visit_record"
	visitapplication "quwoquan_service/services/product-ops-service/internal/product_ops/visit_record/application"
)

const maxVisitRequestBytes = 1 << 10

type Handler struct {
	service *visitapplication.Service
}

// recordVisitRequest mirrors the canonical public RecordVisitRequest body.
// Idempotency-Key is bound from the header and actor identity is derived from
// the verified principal; neither belongs to this JSON body.
type recordVisitRequest struct {
	TargetType string `json:"targetType"`
	TargetKey  string `json:"targetKey"`
}

func NewHandler(service *visitapplication.Service) *Handler {
	if service == nil {
		panic("visit HTTP adapter requires service")
	}
	return &Handler{service: service}
}

func (h *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("visit HTTP adapter requires mux")
	}
	mux.HandleFunc("/ops/visits", h.record)
	mux.HandleFunc("/ops/visits/stats", h.stats)
}

func (h *Handler) record(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		writeRouteNotFound(w, r)
		return
	}
	var request recordVisitRequest
	if err := decodeStrictJSON(r, &request); err != nil {
		writeError(w, r, visitgenerated.AppErrorFromVisitInvalidArgument(err.Error()))
		return
	}
	actorHash, ok := trustedActorHash(r)
	if !ok {
		writeUnauthorized(w, r)
		return
	}
	result, err := h.service.RecordVisit(r.Context(), visitapplication.RecordVisitCommand{
		UserID:     actorHash,
		TargetType: request.TargetType,
		TargetKey:  request.TargetKey,
	}, r.Header.Get("Idempotency-Key"))
	if err != nil {
		writeVisitError(w, r, err, true)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) stats(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRouteNotFound(w, r)
		return
	}
	stats, err := h.service.GetVisitStats(r.Context(), visitapplication.VisitStatsQuery{
		TargetType: r.URL.Query().Get("targetType"),
		TargetKey:  r.URL.Query().Get("targetKey"),
	})
	if err != nil {
		writeVisitError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, stats)
}

func trustedActorHash(r *http.Request) (string, bool) {
	if r == nil {
		return "", false
	}
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", false
	}
	var scopedActor string
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		scopedActor = "persona:" + personaID
	} else if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		scopedActor = "device:" + deviceActorID
	} else {
		return "", false
	}
	sum := sha256.Sum256([]byte(scopedActor))
	return hex.EncodeToString(sum[:]), true
}

func decodeStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxVisitRequestBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain exactly one JSON object")
	}
	return nil
}

func writeVisitError(
	w http.ResponseWriter,
	r *http.Request,
	err error,
	write bool,
) {
	switch {
	case errors.Is(err, visitapplication.ErrInvalidInput),
		errors.Is(err, visitapplication.ErrIdempotencyRequired):
		writeError(w, r, visitgenerated.AppErrorFromVisitInvalidArgument(err.Error()))
	case errors.Is(err, visitapplication.ErrIdempotencyConflict):
		writeError(w, r, visitgenerated.AppErrorFromVisitIdempotencyConflict(err.Error()))
	default:
		if write {
			writeError(w, r, visitgenerated.AppErrorFromVisitStorageWriteFailed(err.Error()))
			return
		}
		writeError(w, r, visitgenerated.AppErrorFromVisitStorageReadFailed(err.Error()))
	}
}

func writeUnauthorized(w http.ResponseWriter, r *http.Request) {
	err := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "unauthorized"),
		"请先登录",
		"verified persona or device actor is required",
	).WithMetadata("unauthorized", http.StatusUnauthorized).WithRecovery("reauth", 0)
	writeError(w, r, err)
}

func writeRouteNotFound(w http.ResponseWriter, r *http.Request) {
	err := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
		"请求地址不存在",
		"visit route or method is not registered",
	).WithMetadata("route_not_found", http.StatusNotFound).WithRecovery("surface", 0)
	writeError(w, r, err)
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

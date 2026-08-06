// Package httpadapter owns the complete Experiment HTTP boundary: canonical
// route registration, strict decoding, application dispatch, wire encoding and
// runtime-error mapping. It does not own ExperimentAssignmentFact routes.
package httpadapter

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rterr "quwoquan_service/runtime/errors"
	experimentgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/experiment"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
)

const maxExperimentRequestBytes = 1 << 20

type Handler struct {
	experiments       *experimentapp.Facade
	assignmentStats   assignmentapp.StatsPort
	collectionPath    string
	rolloutPathPrefix string
	rolloutPathSuffix string
}

type UpdateExperimentRolloutRequest struct {
	Status   string                    `json:"status"`
	Variants []experimentmodel.Variant `json:"variants"`
}

type CreateExperimentRequest struct {
	ID           string                       `json:"id"`
	Key          string                       `json:"key"`
	Status       string                       `json:"status"`
	Variants     []experimentmodel.Variant    `json:"variants"`
	AudienceRule experimentmodel.AudienceRule `json:"audienceRule"`
	StartsAt     string                       `json:"startsAt,omitempty"`
	EndsAt       string                       `json:"endsAt,omitempty"`
}

type ExperimentCatalogItem struct {
	ID                 string                    `json:"id"`
	Key                string                    `json:"key"`
	Status             string                    `json:"status"`
	ExperimentRevision int64                     `json:"experimentRevision"`
	Variants           []experimentmodel.Variant `json:"variants"`
	VariantStats       map[string]int            `json:"variantStats"`
	AssignedSubjects   int                       `json:"assignedSubjects"`
}

type ExperimentCatalogSlice struct {
	Items []ExperimentCatalogItem `json:"items"`
}

type UpdateExperimentRolloutResult struct {
	ID                 string                    `json:"id"`
	Status             string                    `json:"status"`
	ExperimentRevision int64                     `json:"experimentRevision"`
	Variants           []experimentmodel.Variant `json:"variants"`
}

type CreateExperimentResult struct {
	ID                 string                    `json:"id"`
	Key                string                    `json:"key"`
	Status             string                    `json:"status"`
	ExperimentRevision int64                     `json:"experimentRevision"`
	Variants           []experimentmodel.Variant `json:"variants"`
}

func NewHandler(
	experiments *experimentapp.Facade,
	assignmentStats assignmentapp.StatsPort,
) (*Handler, error) {
	if experiments == nil || assignmentStats == nil {
		return nil, errors.New("experiment HTTP adapter requires facade and assignment stats port")
	}
	createMethod, collectionPath := mustExperimentOperationRoute("CreateExperiment")
	listMethod, listPath := mustExperimentOperationRoute("ListExperiments")
	rolloutMethod, rolloutPath := mustExperimentOperationRoute("UpdateExperimentRollout")
	if createMethod != http.MethodPost || listMethod != http.MethodGet ||
		collectionPath != listPath || rolloutMethod != http.MethodPost {
		return nil, errors.New("generated Experiment operation routes are inconsistent")
	}
	rolloutPrefix, rolloutSuffix, err := splitOperationPath(
		rolloutPath,
		"{experimentId}",
	)
	if err != nil {
		return nil, err
	}
	return &Handler{
		experiments: experiments, assignmentStats: assignmentStats,
		collectionPath:    collectionPath,
		rolloutPathPrefix: rolloutPrefix, rolloutPathSuffix: rolloutSuffix,
	}, nil
}

func (h *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("experiment HTTP adapter requires mux")
	}
	mux.Handle(h.collectionPath, h)
	mux.Handle(h.rolloutPathPrefix, h)
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.URL.Path == h.collectionPath && r.Method == http.MethodPost:
		h.createExperiment(w, r)
	case r.URL.Path == h.collectionPath && r.Method == http.MethodGet:
		h.listExperiments(w, r)
	case r.Method == http.MethodPost && h.rolloutExperimentID(r.URL.Path) != "":
		h.updateRollout(w, r)
	default:
		writeRouteNotFound(w, r)
	}
}

func (h *Handler) createExperiment(w http.ResponseWriter, r *http.Request) {
	var command CreateExperimentRequest
	if err := decodeStrictJSON(r, &command); err != nil {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument("Idempotency-Key is required"))
		return
	}
	if _, err := h.experiments.Create(
		r.Context(), command.ID, command.Key, command.Status, command.Variants,
		command.AudienceRule, command.StartsAt, command.EndsAt, idempotencyKey,
	); err != nil {
		writeExperimentError(w, r, err, true)
		return
	}
	created, err := h.experiments.Get(r.Context(), command.ID)
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusCreated, CreateExperimentResult{
		ID: created.ID, Key: created.Key, Status: created.Status,
		ExperimentRevision: created.Version, Variants: created.Variants,
	})
}

func (h *Handler) listExperiments(w http.ResponseWriter, r *http.Request) {
	items, err := h.experiments.List(r.Context())
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	out := make([]ExperimentCatalogItem, 0, len(items))
	for _, item := range items {
		stats, err := h.assignmentStats.StatsForRevision(
			r.Context(),
			item.ID,
			item.Version,
		)
		if err != nil {
			writeExperimentError(w, r, err, false)
			return
		}
		out = append(out, ExperimentCatalogItem{
			ID: item.ID, Key: item.Key, Status: item.Status,
			ExperimentRevision: item.Version, Variants: item.Variants,
			VariantStats: stats.VariantCounts, AssignedSubjects: stats.AssignedSubjects,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	writeJSON(w, http.StatusOK, ExperimentCatalogSlice{Items: out})
}

func (h *Handler) updateRollout(w http.ResponseWriter, r *http.Request) {
	experimentID := h.rolloutExperimentID(r.URL.Path)
	if experimentID == "" {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	var command UpdateExperimentRolloutRequest
	if err := decodeStrictJSON(r, &command); err != nil {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	expectedVersion, err := parseIfMatchVersion(r.Header.Get("If-Match"))
	if err != nil {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument("Idempotency-Key is required"))
		return
	}
	if _, err := h.experiments.UpdateRollout(
		r.Context(), experimentID, expectedVersion, command.Status,
		command.Variants, idempotencyKey,
	); err != nil {
		writeExperimentError(w, r, err, true)
		return
	}
	updated, err := h.experiments.Get(r.Context(), experimentID)
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, UpdateExperimentRolloutResult{
		ID: updated.ID, Status: updated.Status,
		ExperimentRevision: updated.Version, Variants: updated.Variants,
	})
}

func (h *Handler) rolloutExperimentID(path string) string {
	if !strings.HasPrefix(path, h.rolloutPathPrefix) ||
		!strings.HasSuffix(path, h.rolloutPathSuffix) {
		return ""
	}
	value := strings.TrimSuffix(strings.TrimPrefix(path, h.rolloutPathPrefix), h.rolloutPathSuffix)
	if value == "" || strings.Contains(value, "/") {
		return ""
	}
	return value
}

func parseIfMatchVersion(raw string) (int64, error) {
	normalized := strings.TrimSpace(raw)
	normalized = strings.TrimPrefix(normalized, "W/")
	normalized = strings.Trim(normalized, "\"")
	version, err := strconv.ParseInt(normalized, 10, 64)
	if err != nil || version <= 0 {
		return 0, errors.New("If-Match must contain a positive aggregate version")
	}
	return version, nil
}

func writeExperimentError(w http.ResponseWriter, r *http.Request, err error, write bool) {
	switch {
	case errors.Is(err, experimentmodel.ErrInvalidArgument):
		writeError(w, r, experimentgenerated.AppErrorFromInvalidArgument(err.Error()))
	case errors.Is(err, experimentmodel.ErrNotFound):
		writeError(w, r, experimentgenerated.AppErrorFromExperimentNotFound(err.Error()))
	case errors.Is(err, experimentmodel.ErrVersionConflict):
		writeError(w, r, experimentgenerated.AppErrorFromVersionConflict(err.Error()))
	case errors.Is(err, experimentmodel.ErrIdempotencyConflict):
		writeError(w, r, experimentgenerated.AppErrorFromIdempotencyConflict(err.Error()))
	default:
		if write {
			writeError(w, r, experimentgenerated.AppErrorFromStorageWriteFailed(err.Error()))
			return
		}
		writeError(w, r, experimentgenerated.AppErrorFromStorageReadFailed(err.Error()))
	}
}

func decodeStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, maxExperimentRequestBytes+1))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain exactly one JSON object")
	}
	return nil
}

func mustExperimentOperationRoute(operationID string) (string, string) {
	canonicalID := "ops.experiment." + operationID
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if descriptor.CanonicalOperationID == canonicalID {
			return descriptor.Method, descriptor.PathTemplate
		}
	}
	panic(fmt.Sprintf("missing generated Experiment operation descriptor: %s", canonicalID))
}

func splitOperationPath(pathTemplate, placeholder string) (string, string, error) {
	if strings.Count(pathTemplate, placeholder) != 1 {
		return "", "", fmt.Errorf("operation path %q must contain %s exactly once", pathTemplate, placeholder)
	}
	parts := strings.SplitN(pathTemplate, placeholder, 2)
	return parts[0], parts[1], nil
}

func writeRouteNotFound(w http.ResponseWriter, r *http.Request) {
	err := rterr.NewAppError(
		rterr.NewCode(rterr.ModuleGateway, rterr.KindUser, "route_not_found"),
		"请求地址不存在",
		"Experiment route or method is not registered",
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

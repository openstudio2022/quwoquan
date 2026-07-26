package experiment

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"sort"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	productopsgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/experiment"
	experimentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
)

type Handler struct {
	experiments *experimentapp.Facade
	assignments *assignmentapp.Facade
}

type UpdateExperimentRolloutRequest struct {
	Status   string                    `json:"status"`
	Variants []experimentmodel.Variant `json:"variants"`
}

type ExperimentCatalogItem struct {
	ID               string                    `json:"id"`
	Key              string                    `json:"key"`
	Status           string                    `json:"status"`
	PolicyVersion    string                    `json:"policyVersion"`
	Variants         []experimentmodel.Variant `json:"variants"`
	VariantStats     map[string]int            `json:"variantStats"`
	AssignedSubjects int                       `json:"assignedSubjects"`
}

type ExperimentCatalogSlice struct {
	Items []ExperimentCatalogItem `json:"items"`
}

type ExperimentStatsSlice struct {
	ExperimentID     string         `json:"experimentId"`
	PolicyVersion    string         `json:"policyVersion"`
	Status           string         `json:"status"`
	VariantStats     map[string]int `json:"variantStats"`
	AssignedSubjects int            `json:"assignedSubjects"`
}

type UpdateExperimentRolloutResult struct {
	ID            string                    `json:"id"`
	Status        string                    `json:"status"`
	PolicyVersion string                    `json:"policyVersion"`
	Variants      []experimentmodel.Variant `json:"variants"`
}

func NewHandler(experiments *experimentapp.Facade) (*Handler, error) {
	if experiments == nil {
		return nil, errors.New("experiment HTTP adapter requires facade")
	}
	return &Handler{experiments: experiments, assignments: experiments.AssignmentFacts()}, nil
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/control-plane/product/experiments":
		h.listExperiments(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/control-plane/product/experiments/") && strings.HasSuffix(r.URL.Path, ":rollout"):
		h.updateRollout(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/assignment"):
		h.getAssignment(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/assignment"):
		h.assign(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/stats"):
		h.getStats(w, r)
	default:
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experiment route or method is not registered"))
	}
}

func (h *Handler) getAssignment(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/ops/experiments/", "/assignment")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	subjectKey, err := trustedSubjectKey(r)
	if err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromUnauthorized(err.Error()))
		return
	}
	result, err := h.assignments.Get(r.Context(), experimentID, subjectKey)
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) assign(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/ops/experiments/", "/assignment")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	if err := requireEmptyBody(r); err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	subjectKey, err := trustedSubjectKey(r)
	if err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromUnauthorized(err.Error()))
		return
	}
	result, inserted, err := h.assignments.Assign(r.Context(), experimentID, subjectKey)
	if err != nil {
		writeExperimentError(w, r, err, true)
		return
	}
	status := http.StatusOK
	if inserted {
		status = http.StatusCreated
	}
	writeJSON(w, status, result)
}

func (h *Handler) getStats(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/ops/experiments/", "/stats")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	experiment, stats, err := h.assignments.Stats(r.Context(), experimentID)
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, ExperimentStatsSlice{
		ExperimentID: experiment.ID, PolicyVersion: strconv.FormatInt(experiment.Version, 10),
		Status: experiment.Status, VariantStats: stats.VariantCounts,
		AssignedSubjects: stats.AssignedSubjects,
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
		// 目录读已携带当前 policyVersion，统计只做一次分配聚合查询，
		// 不再逐实验重复 Load（N+1 收敛）。
		stats, err := h.experiments.StatsFor(r.Context(), item)
		if err != nil {
			writeExperimentError(w, r, err, false)
			return
		}
		out = append(out, ExperimentCatalogItem{
			ID: item.ID, Key: item.Key, Status: item.Status,
			PolicyVersion: strconv.FormatInt(item.Version, 10), Variants: item.Variants,
			VariantStats: stats.VariantCounts, AssignedSubjects: stats.AssignedSubjects,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	writeJSON(w, http.StatusOK, ExperimentCatalogSlice{Items: out})
}

func (h *Handler) updateRollout(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/control-plane/product/experiments/", ":rollout")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	var command UpdateExperimentRolloutRequest
	if err := decodeStrictJSON(r, &command); err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	expectedVersion, err := parseIfMatchVersion(r.Header.Get("If-Match"))
	if err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("Idempotency-Key is required"))
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
		PolicyVersion: strconv.FormatInt(updated.Version, 10), Variants: updated.Variants,
	})
}

func parseIfMatchVersion(raw string) (int64, error) {
	normalized := strings.TrimSpace(raw)
	normalized = strings.TrimPrefix(normalized, "W/")
	normalized = strings.Trim(normalized, "\"")
	version, err := strconv.ParseInt(normalized, 10, 64)
	if err != nil || version <= 0 {
		return 0, fmt.Errorf("If-Match must contain a positive aggregate version")
	}
	return version, nil
}

func trustedSubjectKey(r *http.Request) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	if !ok {
		return "", errors.New("verified persona or device principal is required")
	}
	if personaID := strings.TrimSpace(principal.Actor.PersonaID); personaID != "" {
		return "persona:" + personaID, nil
	}
	if deviceActorID := strings.TrimSpace(principal.Actor.DeviceActorID); deviceActorID != "" {
		return "device:" + deviceActorID, nil
	}
	return "", errors.New("verified persona or device principal is required")
}

func writeExperimentError(w http.ResponseWriter, r *http.Request, err error, write bool) {
	switch {
	case errors.Is(err, experimentmodel.ErrNotFound):
		writeError(w, r, productopsgenerated.AppErrorFromExperimentNotFound(err.Error()))
	case errors.Is(err, experimentmodel.ErrAssignmentNotFound):
		writeError(w, r, productopsgenerated.AppErrorFromAssignmentNotFound(err.Error()))
	case errors.Is(err, experimentmodel.ErrDisabled):
		writeError(w, r, productopsgenerated.AppErrorFromExperimentNotRunning(err.Error()))
	case errors.Is(err, experimentmodel.ErrVersionConflict):
		writeError(w, r, productopsgenerated.AppErrorFromVersionConflict(err.Error()))
	case errors.Is(err, experimentmodel.ErrIdempotencyConflict):
		writeError(w, r, productopsgenerated.AppErrorFromIdempotencyConflict(err.Error()))
	default:
		if write {
			writeError(w, r, productopsgenerated.AppErrorFromStorageWriteFailed(err.Error()))
			return
		}
		writeError(w, r, productopsgenerated.AppErrorFromStorageReadFailed(err.Error()))
	}
}

func decodeStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	if err := decoder.Decode(&struct{}{}); !errors.Is(err, io.EOF) {
		return errors.New("request body must contain one JSON object")
	}
	return nil
}

func requireEmptyBody(r *http.Request) error {
	payload, err := io.ReadAll(io.LimitReader(r.Body, 1025))
	if err != nil {
		return fmt.Errorf("read request body: %w", err)
	}
	if len(payload) > 1024 || strings.TrimSpace(string(payload)) != "" {
		return errors.New("request body is not allowed")
	}
	return nil
}

func segmentBetween(path, prefix, suffix string) string {
	value := strings.TrimPrefix(path, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.Trim(value, "/")
}

func writeJSON(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

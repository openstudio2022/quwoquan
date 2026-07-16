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
	experimentapp "quwoquan_service/services/product-ops-service/internal/application/product_ops/experiment"
	experimentmodel "quwoquan_service/services/product-ops-service/internal/domain/product_ops/experiment/model"
	productopsgenerated "quwoquan_service/services/product-ops-service/internal/generated"
)

type Handler struct {
	experiments *experimentapp.Facade
}

type UpdateExperimentRolloutRequest struct {
	ExpectedVersion int64                     `json:"expectedVersion"`
	Status          string                    `json:"status"`
	Variants        []experimentmodel.Variant `json:"variants"`
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
	return &Handler{experiments: experiments}, nil
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.Path == "/v1/control-plane/product/experiments":
		h.listExperiments(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/control-plane/product/experiments/") && strings.HasSuffix(r.URL.Path, ":rollout"):
		h.updateRollout(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/v1/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/assignment"):
		h.getAssignment(w, r)
	case r.Method == http.MethodPost && strings.HasPrefix(r.URL.Path, "/v1/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/assignment"):
		h.assign(w, r)
	case r.Method == http.MethodGet && strings.HasPrefix(r.URL.Path, "/v1/ops/experiments/") && strings.HasSuffix(r.URL.Path, "/stats"):
		h.getStats(w, r)
	default:
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experiment route or method is not registered"))
	}
}

func (h *Handler) getAssignment(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/assignment")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	subjectKey, err := trustedSubjectKey(r)
	if err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromUnauthorized(err.Error()))
		return
	}
	result, err := h.experiments.GetAssignment(r.Context(), experimentID, subjectKey)
	if err != nil {
		writeExperimentError(w, r, err, false)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) assign(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/assignment")
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
	result, inserted, err := h.experiments.Assign(r.Context(), experimentID, subjectKey)
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
	experimentID := segmentBetween(r.URL.Path, "/v1/ops/experiments/", "/stats")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	experiment, stats, err := h.experiments.Stats(r.Context(), experimentID)
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
		current, stats, err := h.experiments.Stats(r.Context(), item.ID)
		if err != nil {
			writeExperimentError(w, r, err, false)
			return
		}
		out = append(out, ExperimentCatalogItem{
			ID: current.ID, Key: current.Key, Status: current.Status,
			PolicyVersion: strconv.FormatInt(current.Version, 10), Variants: current.Variants,
			VariantStats: stats.VariantCounts, AssignedSubjects: stats.AssignedSubjects,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	writeJSON(w, http.StatusOK, ExperimentCatalogSlice{Items: out})
}

func (h *Handler) updateRollout(w http.ResponseWriter, r *http.Request) {
	experimentID := segmentBetween(r.URL.Path, "/v1/control-plane/product/experiments/", ":rollout")
	if experimentID == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("experimentId is required"))
		return
	}
	var command UpdateExperimentRolloutRequest
	if err := decodeStrictJSON(r, &command); err != nil {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument(err.Error()))
		return
	}
	if command.ExpectedVersion <= 0 {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("expectedVersion must be positive"))
		return
	}
	idempotencyKey := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	if idempotencyKey == "" {
		writeError(w, r, productopsgenerated.AppErrorFromInvalidArgument("Idempotency-Key is required"))
		return
	}
	if _, err := h.experiments.UpdateRollout(
		r.Context(), experimentID, command.ExpectedVersion, command.Status,
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

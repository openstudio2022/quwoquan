// Package httpadapter owns the complete ExperimentAssignmentFact HTTP
// boundary. Experiment policy access is available only through the object's
// application facade and Experiment's public application port.
package httpadapter

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	assignmentgenerated "quwoquan_service/services/product-ops-service/generated/product_ops/experiment_assignment_fact"
	assignmentapp "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

const maxAssignmentQueryBodyBytes = 1 << 10

type Handler struct {
	service          *assignmentapp.Facade
	pathPrefix       string
	assignmentSuffix string
	statsSuffix      string
}

type ExperimentStatsSlice struct {
	ExperimentID       string         `json:"experimentId"`
	ExperimentRevision int64          `json:"experimentRevision"`
	Status             string         `json:"status"`
	VariantStats       map[string]int `json:"variantStats"`
	AssignedSubjects   int            `json:"assignedSubjects"`
}

func NewHandler(service *assignmentapp.Facade) (*Handler, error) {
	if service == nil {
		return nil, errors.New("ExperimentAssignmentFact HTTP adapter requires facade")
	}
	assignmentMethod, assignmentPath := mustAssignmentOperationRoute("GetExperimentAssignment")
	statsMethod, statsPath := mustAssignmentOperationRoute("GetExperimentStats")
	if assignmentMethod != http.MethodGet || statsMethod != http.MethodGet {
		return nil, errors.New("generated ExperimentAssignmentFact operation methods are inconsistent")
	}
	assignmentPrefix, assignmentSuffix, err := splitOperationPath(
		assignmentPath,
		"{experimentId}",
	)
	if err != nil {
		return nil, err
	}
	statsPrefix, statsSuffix, err := splitOperationPath(statsPath, "{experimentId}")
	if err != nil {
		return nil, err
	}
	if assignmentPrefix != statsPrefix {
		return nil, errors.New("ExperimentAssignmentFact routes must share the canonical object prefix")
	}
	return &Handler{
		service: service, pathPrefix: assignmentPrefix,
		assignmentSuffix: assignmentSuffix, statsSuffix: statsSuffix,
	}, nil
}

func (h *Handler) Register(mux *http.ServeMux) {
	if mux == nil {
		panic("ExperimentAssignmentFact HTTP adapter requires mux")
	}
	mux.Handle(h.pathPrefix, h)
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		writeRouteNotFound(w, r)
		return
	}
	switch {
	case h.experimentID(r.URL.Path, h.assignmentSuffix) != "":
		h.getAssignment(w, r)
	case h.experimentID(r.URL.Path, h.statsSuffix) != "":
		h.getStats(w, r)
	default:
		writeRouteNotFound(w, r)
	}
}

func (h *Handler) getAssignment(w http.ResponseWriter, r *http.Request) {
	if err := requireEmptyBody(r); err != nil {
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentInvalidArgument(err.Error()))
		return
	}
	experimentID := h.experimentID(r.URL.Path, h.assignmentSuffix)
	if experimentID == "" {
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentInvalidArgument("experimentId is required"))
		return
	}
	subjectKey, err := trustedSubjectKey(r)
	if err != nil {
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentUnauthorized(err.Error()))
		return
	}
	result, err := h.service.Get(r.Context(), experimentID, subjectKey)
	if err != nil {
		writeApplicationError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func (h *Handler) getStats(w http.ResponseWriter, r *http.Request) {
	if err := requireEmptyBody(r); err != nil {
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentInvalidArgument(err.Error()))
		return
	}
	experimentID := h.experimentID(r.URL.Path, h.statsSuffix)
	if experimentID == "" {
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentInvalidArgument("experimentId is required"))
		return
	}
	policy, stats, err := h.service.Stats(r.Context(), experimentID)
	if err != nil {
		writeApplicationError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, ExperimentStatsSlice{
		ExperimentID: policy.ID, ExperimentRevision: policy.Revision,
		Status: policy.Status, VariantStats: stats.VariantCounts,
		AssignedSubjects: stats.AssignedSubjects,
	})
}

func (h *Handler) experimentID(path, suffix string) string {
	if !strings.HasPrefix(path, h.pathPrefix) || !strings.HasSuffix(path, suffix) {
		return ""
	}
	value := strings.TrimSuffix(strings.TrimPrefix(path, h.pathPrefix), suffix)
	if value == "" || strings.Contains(value, "/") {
		return ""
	}
	return value
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

func writeApplicationError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, assignmentapp.ErrExperimentNotFound):
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentExperimentNotFound(err.Error()))
	case errors.Is(err, assignmentdomain.ErrNotFound):
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentNotFound(err.Error()))
	default:
		writeError(w, r, assignmentgenerated.AppErrorFromExperimentAssignmentStorageReadFailed(err.Error()))
	}
}

func requireEmptyBody(r *http.Request) error {
	payload, err := io.ReadAll(io.LimitReader(r.Body, maxAssignmentQueryBodyBytes+1))
	if err != nil {
		return fmt.Errorf("read request body: %w", err)
	}
	if len(payload) > maxAssignmentQueryBodyBytes || strings.TrimSpace(string(payload)) != "" {
		return errors.New("request body is not allowed")
	}
	return nil
}

func mustAssignmentOperationRoute(operationID string) (string, string) {
	canonicalID := "ops.experiment_assignment_fact." + operationID
	for _, descriptor := range operationsecurity.ForDomain("ops") {
		if descriptor.CanonicalOperationID == canonicalID {
			return descriptor.Method, descriptor.PathTemplate
		}
	}
	panic(fmt.Sprintf("missing generated ExperimentAssignmentFact operation descriptor: %s", canonicalID))
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
		"ExperimentAssignmentFact route or method is not registered",
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

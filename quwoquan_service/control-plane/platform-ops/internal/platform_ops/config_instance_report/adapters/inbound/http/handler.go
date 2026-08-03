package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strings"
	"time"

	configreportgenerated "quwoquan_service/control-plane/platform-ops/generated/platform_ops/config_instance_report"
	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	reportmodel "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/domain/model"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/controlplane"
	rterr "quwoquan_service/runtime/errors"
)

var canonicalSHA256 = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)

type Handler struct {
	commands        *reportapp.CommandFacade
	queries         *reportapp.QueryFacade
	candidateDigest string
}

func NewHandler(
	commands *reportapp.CommandFacade,
	queries *reportapp.QueryFacade,
	candidateDigest string,
) (*Handler, error) {
	if commands == nil || queries == nil {
		return nil, errors.New("config instance report handler requires command and query facades")
	}
	return &Handler{
		commands: commands, queries: queries,
		candidateDigest: strings.TrimSpace(candidateDigest),
	}, nil
}

func (handler *Handler) Routes(mux *http.ServeMux) {
	mux.Handle("/control-plane/platform/configs/instances", handler)
	mux.Handle("/control-plane/platform/configs/instances/", handler)
}

func (handler *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/control-plane/platform/configs/instances" {
		handler.list(w, r)
		return
	}
	handler.report(w, r)
}

func (handler *Handler) list(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.NotFound(w, r)
		return
	}
	reports, err := handler.queries.List(r.Context())
	if err != nil {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportStorageFailed(err.Error()))
		return
	}
	documents := make([]controlplane.Document, 0, len(reports))
	for _, report := range reports {
		documents = append(documents, reportDocument(report))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items": reports, "summary": controlplane.SummarizeConfigDrift(documents),
	})
}

func (handler *Handler) report(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost || !strings.HasSuffix(r.URL.Path, ":report") {
		http.NotFound(w, r)
		return
	}
	instanceID := segmentBetween(
		r.URL.Path,
		"/control-plane/platform/configs/instances/",
		":report",
	)
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	trustedService, trustedEnvironment, identityErr := trustedServiceIdentity(
		principal,
		ok,
		instanceID,
	)
	if identityErr != nil {
		writeUnauthorized(w, r, identityErr.Error())
		return
	}
	if !canonicalSHA256.MatchString(handler.candidateDigest) {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportCandidateUnavailable(
			"control-plane release manifest digest is unavailable",
		))
		return
	}
	var input reportmodel.Report
	if err := json.NewDecoder(r.Body).Decode(&input); err != nil {
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid(
			"decode report: "+err.Error(),
		))
		return
	}
	input.InstanceID = instanceID
	report, err := handler.commands.Report(
		r.Context(),
		input,
		trustedService,
		trustedEnvironment,
		handler.candidateDigest,
		reportapp.CommandContext{
			Actor:       strings.TrimSpace(principal.Actor.AccountID),
			Environment: trustedEnvironment,
			RequestID:   strings.TrimSpace(r.Header.Get("X-Request-Id")),
			TraceID:     strings.TrimSpace(r.Header.Get("X-Trace-Id")),
		},
	)
	if err != nil {
		writeReportError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, report)
}

func trustedServiceIdentity(
	principal rtauth.Principal,
	found bool,
	instanceID string,
) (string, string, error) {
	if !found || !contains(principal.Roles, "service") {
		return "", "", errors.New("service principal is required")
	}
	const prefix = "service:"
	subject := strings.TrimSpace(principal.Actor.AccountID)
	if !strings.HasPrefix(subject, prefix) {
		return "", "", errors.New("service principal is required")
	}
	service, environment, ok := strings.Cut(strings.TrimPrefix(subject, prefix), "@")
	service = strings.TrimSpace(service)
	environment = strings.TrimSpace(environment)
	if !ok || service == "" || environment == "" ||
		!strings.HasPrefix(strings.TrimSpace(instanceID), service+"-") {
		return "", "", errors.New("service principal does not own the instance namespace")
	}
	return service, environment, nil
}

func writeReportError(w http.ResponseWriter, r *http.Request, err error) {
	switch {
	case errors.Is(err, reportmodel.ErrInvalidIdentity):
		writeUnauthorized(w, r, err.Error())
	case errors.Is(err, reportmodel.ErrCandidateConflict),
		errors.Is(err, reportmodel.ErrDesiredConflict),
		errors.Is(err, controlplane.ErrMutationIdempotencyConflict):
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportConflict(err.Error()))
	case errors.Is(err, reportmodel.ErrInvalidReport):
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportInvalid(err.Error()))
	default:
		writeError(w, r, configreportgenerated.AppErrorFromConfigInstanceReportStorageFailed(err.Error()))
	}
}

func writeUnauthorized(w http.ResponseWriter, r *http.Request, debug string) {
	writeError(
		w,
		r,
		configreportgenerated.AppErrorFromConfigInstanceReportUnauthorized(debug),
	)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func segmentBetween(value string, prefix string, suffix string) string {
	value = strings.TrimPrefix(value, prefix)
	value = strings.TrimSuffix(value, suffix)
	return strings.TrimSpace(value)
}

func contains(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func reportDocument(report reportmodel.Report) controlplane.Document {
	return controlplane.Document{
		"id": report.InstanceID, "instanceId": report.InstanceID,
		"environment": report.Environment, "cluster": report.Cluster,
		"service": report.Service, "configVersion": report.ConfigVersion,
		"imageVersion":          report.ImageVersion,
		"releaseManifestDigest": report.ReleaseManifestDigest,
		"desiredHash":           report.DesiredHash, "effectiveHash": report.EffectiveHash,
		"inSync": report.InSync, "source": report.Source,
		"updatedAt": report.UpdatedAt.UTC().Format(time.RFC3339Nano),
		"lastError": report.LastError,
	}
}

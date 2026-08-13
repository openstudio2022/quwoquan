package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	packageerrors "quwoquan_service/services/assistant-service/generated/assistant/skill_package_release"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

const maxRequestBodyBytes = 4 << 20

type Handler struct{ service *packageapplication.Service }

type activateCommand struct {
	PackageID         string                         `json:"packageId"`
	ReleaseDigest     string                         `json:"releaseDigest"`
	ExpectedRevision  int                            `json:"expectedRevision"`
	EvaluationReceipt packagemodel.EvaluationReceipt `json:"evaluationReceipt"`
}

type rollbackCommand struct {
	PackageID        string `json:"packageId"`
	ExpectedRevision int    `json:"expectedRevision"`
}

func NewHandler(service *packageapplication.Service) *Handler {
	return &Handler{service: service}
}

func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("POST /internal/assistant/skill-package-releases", h.stage)
	mux.HandleFunc("POST /internal/assistant/skill-package-releases:activate", h.activate)
	mux.HandleFunc("POST /internal/assistant/skill-package-releases:rollback", h.rollback)
}

func (h *Handler) stage(w http.ResponseWriter, r *http.Request) {
	commandID, _, err := commandIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var release packagemodel.Release
	if err := decode(w, r, &release); err != nil {
		writeError(w, r, packageerrors.AppErrorFromSkillPackageInvalid(err.Error()))
		return
	}
	result, err := h.service.Stage(r.Context(), commandID, release)
	if err != nil {
		writeError(w, r, mapError(err))
		return
	}
	writeJSON(w, http.StatusCreated, result.Release)
}

func (h *Handler) activate(w http.ResponseWriter, r *http.Request) {
	commandID, publisherID, err := commandIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input activateCommand
	if err := decode(w, r, &input); err != nil {
		writeError(w, r, packageerrors.AppErrorFromSkillPackageInvalid(err.Error()))
		return
	}
	result, err := h.service.Activate(r.Context(), commandID, packageapplication.ActivateInput{
		PackageID: input.PackageID, ReleaseDigest: input.ReleaseDigest,
		ExpectedRevision: input.ExpectedRevision, ActivatedBy: publisherID,
		EvaluationReceipt: input.EvaluationReceipt,
	})
	if err != nil {
		writeError(w, r, mapError(err))
		return
	}
	writeJSON(w, http.StatusOK, result.Activation)
}

func (h *Handler) rollback(w http.ResponseWriter, r *http.Request) {
	commandID, publisherID, err := commandIdentity(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var input rollbackCommand
	if err := decode(w, r, &input); err != nil {
		writeError(w, r, packageerrors.AppErrorFromSkillPackageInvalid(err.Error()))
		return
	}
	result, err := h.service.Rollback(r.Context(), commandID, packageapplication.RollbackInput{
		PackageID: input.PackageID, ExpectedRevision: input.ExpectedRevision,
		ActivatedBy: publisherID,
	})
	if err != nil {
		writeError(w, r, mapError(err))
		return
	}
	writeJSON(w, http.StatusOK, result.Activation)
}

func commandIdentity(r *http.Request) (string, string, error) {
	commandID := strings.TrimSpace(r.Header.Get("Idempotency-Key"))
	principal, ok := rtauth.PrincipalFromContext(r.Context())
	publisherID := strings.TrimSpace(principal.Subject)
	if !ok || publisherID == "" || commandID == "" {
		return "", "", packageerrors.AppErrorFromSkillPackageInvalid(
			"trusted service publisher and Idempotency-Key are required",
		)
	}
	return commandID, publisherID, nil
}

func decode(w http.ResponseWriter, r *http.Request, value any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxRequestBodyBytes))
	decoder.DisallowUnknownFields()
	return decoder.Decode(value)
}

func mapError(err error) error {
	switch {
	case errors.Is(err, packagemodel.ErrEvaluationReceiptInvalid):
		return packageerrors.AppErrorFromSkillPackageEvaluationReceiptInvalid(err.Error())
	case errors.Is(err, packagemodel.ErrDigestMismatch),
		errors.Is(err, packagemodel.ErrAssetMismatch):
		return packageerrors.AppErrorFromSkillPackageDigestMismatch(err.Error())
	case errors.Is(err, packagemodel.ErrRevisionConflict):
		return packageerrors.AppErrorFromSkillPackageRevisionConflict(err.Error())
	case errors.Is(err, packagemodel.ErrCapabilityDenied):
		return packageerrors.AppErrorFromSkillPackageCapabilityDenied(err.Error())
	case errors.Is(err, packagemodel.ErrSignatureInvalid):
		return packageerrors.AppErrorFromSkillPackageSignatureInvalid(err.Error())
	case errors.Is(err, packagemodel.ErrReleaseNotFound),
		errors.Is(err, packagemodel.ErrActivationAbsent),
		errors.Is(err, packagemodel.ErrAssetUnavailable):
		return packageerrors.AppErrorFromSkillPackageAssetUnavailable(err.Error())
	default:
		return packageerrors.AppErrorFromSkillPackageInvalid(err.Error())
	}
}

func writeJSON(w http.ResponseWriter, status int, value any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(value)
}

func writeError(w http.ResponseWriter, r *http.Request, err error) {
	rterr.WriteHTTPError(w, err, rterr.HTTPWriteOptionsFromRequest(r))
}

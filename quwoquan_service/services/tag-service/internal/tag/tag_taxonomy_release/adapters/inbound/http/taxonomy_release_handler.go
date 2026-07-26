package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	rterrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/application/taxonomyrelease"
	releasemodel "quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
)

// TaxonomyReleaseHandler 承载 internal publish plane 的两条命令路由
// （Data publish 管道专属；auth_mode required + service principal 由网关/内网边界保证）。
type TaxonomyReleaseHandler struct {
	facade *taxonomyrelease.Facade
}

func NewTaxonomyReleaseHandler(facade *taxonomyrelease.Facade) *TaxonomyReleaseHandler {
	return &TaxonomyReleaseHandler{facade: facade}
}

func (h *TaxonomyReleaseHandler) Register(mux *http.ServeMux) {
	mux.HandleFunc("POST /internal/tag/taxonomy-releases", h.handleStage)
	mux.HandleFunc("POST /internal/tag/taxonomy-releases/{releaseId}", h.handleActivate)
}

func (h *TaxonomyReleaseHandler) handleStage(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ReleaseID       string `json:"releaseId"`
		SourceOwner     string `json:"sourceOwner"`
		CanonicalDigest string `json:"canonicalDigest"`
		NodeCount       int    `json:"nodeCount"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeTagError(w, r, releaseInvalidArgument("decode stage body: "+err.Error()))
		return
	}
	release, err := h.facade.Stage(r.Context(), taxonomyrelease.StageCommand{
		ReleaseID:       body.ReleaseID,
		SourceOwner:     body.SourceOwner,
		CanonicalDigest: body.CanonicalDigest,
		NodeCount:       body.NodeCount,
	})
	if err != nil {
		writeTagError(w, r, mapReleaseError(err))
		return
	}
	writeJSON(w, http.StatusOK, release)
}

func (h *TaxonomyReleaseHandler) handleActivate(w http.ResponseWriter, r *http.Request) {
	// path 形如 /internal/tag/taxonomy-releases/{releaseId}:activate
	raw := strings.TrimSpace(r.PathValue("releaseId"))
	releaseID, ok := strings.CutSuffix(raw, ":activate")
	if !ok || strings.TrimSpace(releaseID) == "" {
		writeTagError(w, r, releaseInvalidArgument("activate path requires {releaseId}:activate"))
		return
	}
	release, err := h.facade.Activate(r.Context(), releaseID)
	if err != nil {
		writeTagError(w, r, mapReleaseError(err))
		return
	}
	writeJSON(w, http.StatusOK, release)
}

// mapReleaseError 把领域错误映射为 tag/tag/tag_taxonomy_release/errors.yaml 声明的稳定错误。
func mapReleaseError(err error) error {
	switch {
	case errors.Is(err, releasemodel.ErrInvalidArgument):
		return releaseInvalidArgument(err.Error())
	case errors.Is(err, releasemodel.ErrNotFound):
		return releaseError("release_not_found", "标签发布批次不存在", http.StatusNotFound, err)
	case errors.Is(err, releasemodel.ErrInvalidTransition):
		return releaseError("release_invalid_transition", "标签发布状态不允许该操作", http.StatusConflict, err)
	case errors.Is(err, releasemodel.ErrSnapshotIncomplete):
		return releaseError("release_snapshot_incomplete", "标签快照尚未完整导入，暂不能激活", http.StatusConflict, err)
	case errors.Is(err, releasemodel.ErrVersionConflict):
		return releaseError("release_version_conflict", "标签发布已更新，请刷新后重试", http.StatusConflict, err)
	case errors.Is(err, releasemodel.ErrDigestConflict):
		return releaseError("release_idempotency_conflict", "重复请求与原发布操作不一致", http.StatusConflict, err)
	default:
		return releaseError("release_storage_failed", "标签发布操作失败，请稍后重试", http.StatusInternalServerError, err)
	}
}

func releaseInvalidArgument(debug string) error {
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, rterrors.KindUser, "release_invalid_argument"),
		"标签发布请求不合法", debug)
	appErr.HTTPStatus = http.StatusBadRequest
	return appErr
}

func releaseError(reason, userMessage string, status int, err error) error {
	kind := rterrors.KindUser
	if status >= 500 {
		kind = rterrors.KindSystem
	}
	appErr := rterrors.NewAppError(
		rterrors.NewCode(moduleTag, kind, reason), userMessage, err.Error())
	appErr.HTTPStatus = status
	return appErr
}

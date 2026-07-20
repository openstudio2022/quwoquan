package http

import (
	"errors"
	"net/http"
	"strings"

	filtercatalogapp "quwoquan_service/services/content-service/internal/application/content/filter_catalog_release"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/domain/content/filter_catalog_release/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type stageFilterCatalogReleaseBody struct {
	ReleaseID                    string                                        `json:"releaseId"`
	SourceOwner                  string                                        `json:"sourceOwner"`
	CanonicalDigest              string                                        `json:"canonicalDigest"`
	Categories                   []filtercatalogmodel.FilterCategoryDefinition `json:"categories"`
	Presets                      []filtercatalogmodel.FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                                      `json:"recommendedFallbackPresetIds"`
}

func (handler *ContentHandler) handleStageFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.filterCatalogService == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	body, err := decodeFilterCatalogStageBody(request)
	if err != nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogInvalidArgument("decode StageFilterCatalogRelease: "+err.Error()),
		)
		return
	}
	result, err := handler.filterCatalogService.Stage(
		request.Context(),
		filtercatalogapp.StageFilterCatalogReleaseCommand{
			ReleaseID:                    body.ReleaseID,
			SourceOwner:                  body.SourceOwner,
			CanonicalDigest:              body.CanonicalDigest,
			Categories:                   body.Categories,
			Presets:                      body.Presets,
			RecommendedFallbackPresetIDs: body.RecommendedFallbackPresetIDs,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, mapFilterCatalogError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Release)
}

func (handler *ContentHandler) handleActivateFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.filterCatalogService == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	result, err := handler.filterCatalogService.Activate(
		request.Context(),
		filtercatalogapp.ActivateFilterCatalogReleaseCommand{
			ReleaseID: strings.TrimSpace(request.PathValue("releaseId")),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, mapFilterCatalogError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Release)
}

func (handler *ContentHandler) handleRollbackFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.filterCatalogService == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	result, err := handler.filterCatalogService.Rollback(
		request.Context(),
		filtercatalogapp.RollbackFilterCatalogReleaseCommand{
			ReleaseID: strings.TrimSpace(request.PathValue("releaseId")),
		},
	)
	if err != nil {
		writeHTTPError(writer, request, mapFilterCatalogError(err))
		return
	}
	writeJSON(writer, http.StatusOK, result.Release)
}

func (handler *ContentHandler) handleGetActiveFilterCatalog(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.filterCatalogService == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	catalog, err := handler.filterCatalogService.GetActiveFilterCatalog(request.Context())
	if err != nil {
		writeHTTPError(writer, request, mapFilterCatalogError(err))
		return
	}
	writeJSON(writer, http.StatusOK, catalog)
}

func mapFilterCatalogError(err error) error {
	switch {
	case errors.Is(err, filtercatalogmodel.ErrInvalidArgument):
		return filterCatalogInvalidArgument(err.Error())
	case errors.Is(err, filtercatalogmodel.ErrDigestMismatch):
		return contentgenerated.AppErrorFromFilterCatalogDigestMismatch(err.Error())
	case errors.Is(err, filtercatalogmodel.ErrReleaseNotFound):
		return contentgenerated.AppErrorFromFilterCatalogReleaseNotFound(err.Error())
	case errors.Is(err, filtercatalogmodel.ErrInvalidTransition):
		return contentgenerated.AppErrorFromFilterCatalogInvalidTransition(err.Error())
	case errors.Is(err, filtercatalogmodel.ErrIdempotencyConflict):
		return contentgenerated.AppErrorFromFilterCatalogIdempotencyConflict(err.Error())
	case errors.Is(err, filtercatalogmodel.ErrCatalogUnavailable):
		return contentgenerated.AppErrorFromFilterCatalogUnavailable(err.Error())
	default:
		return filterCatalogStorageUnavailable(err.Error())
	}
}

func filterCatalogInvalidArgument(debugMessage string) error {
	return contentgenerated.AppErrorFromFilterCatalogInvalidArgument(debugMessage)
}

func filterCatalogStorageUnavailable(debugMessage string) error {
	return contentgenerated.AppErrorFromFilterCatalogStorageUnavailable(debugMessage)
}

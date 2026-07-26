package http

import (
	"errors"
	"net/http"
	"strings"

	contentgenerated "quwoquan_service/services/content-service/generated/media/filter_catalog_release"
	filtercatalogtransport "quwoquan_service/services/content-service/generated/media/filter_catalog_release/transport"
	filtercatalogapp "quwoquan_service/services/content-service/internal/media/filter_catalog_release/application"
	filtercatalogmodel "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/model"
)

type Handler struct {
	facades *filtercatalogapp.Facades
}

func NewHandler(facades *filtercatalogapp.Facades) *Handler {
	return &Handler{facades: facades}
}

func (handler *Handler) Stage(writer http.ResponseWriter, request *http.Request) {
	handler.handleStageFilterCatalogRelease(writer, request)
}

func (handler *Handler) Activate(writer http.ResponseWriter, request *http.Request) {
	handler.handleActivateFilterCatalogRelease(writer, request)
}

func (handler *Handler) Rollback(writer http.ResponseWriter, request *http.Request) {
	handler.handleRollbackFilterCatalogRelease(writer, request)
}

func (handler *Handler) GetActive(writer http.ResponseWriter, request *http.Request) {
	handler.handleGetActiveFilterCatalog(writer, request)
}

// Route dispatches FilterCatalogRelease routes and delegates all other routes
// to the service-level composition handler.
func (handler *Handler) Route(next http.Handler) http.Handler {
	if next == nil {
		next = http.NotFoundHandler()
	}
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		operation, ok := filtercatalogtransport.ResolveOperation(request)
		if !ok {
			next.ServeHTTP(writer, request)
			return
		}
		request = request.WithContext(filtercatalogapp.WithIdempotencyKey(
			request.Context(),
			strings.TrimSpace(request.Header.Get("Idempotency-Key")),
		))
		handler.dispatch(operation, writer, request)
	})
}

func (handler *Handler) dispatch(
	operation string,
	writer http.ResponseWriter,
	request *http.Request,
) {
	switch operation {
	case "StageFilterCatalogRelease":
		handler.handleStageFilterCatalogRelease(writer, request)
	case "ActivateFilterCatalogRelease":
		handler.handleActivateFilterCatalogRelease(writer, request)
	case "RollbackFilterCatalogRelease":
		handler.handleRollbackFilterCatalogRelease(writer, request)
	case "GetActiveFilterCatalog":
		handler.handleGetActiveFilterCatalog(writer, request)
	default:
		writeHTTPError(
			writer,
			request,
			filterCatalogInvalidArgument("unsupported FilterCatalogRelease operation: "+operation),
		)
	}
}

type stageFilterCatalogReleaseBody struct {
	ReleaseID                    string                                        `json:"releaseId"`
	SourceOwner                  string                                        `json:"sourceOwner"`
	CanonicalDigest              string                                        `json:"canonicalDigest"`
	Categories                   []filtercatalogmodel.FilterCategoryDefinition `json:"categories"`
	Presets                      []filtercatalogmodel.FilterPresetDefinition   `json:"presets"`
	RecommendedFallbackPresetIDs []string                                      `json:"recommendedFallbackPresetIds"`
}

func (handler *Handler) handleStageFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.facades == nil {
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
	result, err := handler.facades.Stage(
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

func (handler *Handler) handleActivateFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.facades == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	result, err := handler.facades.Activate(
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

func (handler *Handler) handleRollbackFilterCatalogRelease(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.facades == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	result, err := handler.facades.Rollback(
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

func (handler *Handler) handleGetActiveFilterCatalog(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.facades == nil {
		writeHTTPError(
			writer,
			request,
			filterCatalogStorageUnavailable("FilterCatalogRelease facades are not configured"),
		)
		return
	}
	catalog, err := handler.facades.GetActiveFilterCatalog(request.Context())
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

package http

import (
	"errors"
	"net/http"
	"strings"

	mediareprocessapp "quwoquan_service/services/content-service/internal/application/media/reprocess"
	reprocessmodel "quwoquan_service/services/content-service/internal/domain/media_reprocess/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

type startMediaImageReprocessRunBody struct {
	RunID    string   `json:"runId"`
	AssetIDs []string `json:"assetIds"`
}

func (handler *ContentHandler) handleStartMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.mediaImageReprocessService == nil {
		writeHTTPError(writer, request, mediaImageReprocessUnavailable("MediaImageReprocessRun service is not configured"))
		return
	}
	var body startMediaImageReprocessRunBody
	if err := decodeRequiredJSONBody(request, &body); err != nil {
		writeHTTPError(writer, request, mediaImageReprocessInvalidArgument(err.Error()))
		return
	}
	run, _, err := handler.mediaImageReprocessService.Start(
		request.Context(),
		mediareprocessapp.StartCommand{RunID: body.RunID, AssetIDs: body.AssetIDs},
		contentgenerated.ContentImageDerivativePolicyVersion,
	)
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	writeJSON(writer, http.StatusAccepted, run.Snapshot())
}

func (handler *ContentHandler) handlePauseMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transitionMediaImageReprocessRun(writer, request, "pause")
}

func (handler *ContentHandler) handleResumeMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transitionMediaImageReprocessRun(writer, request, "resume")
}

func (handler *ContentHandler) handleRollbackMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transitionMediaImageReprocessRun(writer, request, "rollback")
}

func (handler *ContentHandler) transitionMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
	operation string,
) {
	if handler.mediaImageReprocessService == nil {
		writeHTTPError(writer, request, mediaImageReprocessUnavailable("MediaImageReprocessRun service is not configured"))
		return
	}
	runID := strings.TrimSpace(request.PathValue("runId"))
	var (
		run *reprocessmodel.Run
		err error
	)
	switch operation {
	case "pause":
		run, _, err = handler.mediaImageReprocessService.Pause(request.Context(), runID)
	case "resume":
		run, _, err = handler.mediaImageReprocessService.Resume(request.Context(), runID)
	case "rollback":
		run, _, err = handler.mediaImageReprocessService.StartRollback(request.Context(), runID)
	default:
		err = errors.New("unknown media image reprocess transition")
	}
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	writeJSON(writer, http.StatusAccepted, run.Snapshot())
}

func (handler *ContentHandler) handleGetMediaImageReprocessRun(
	writer http.ResponseWriter,
	request *http.Request,
) {
	if handler.mediaImageReprocessService == nil {
		writeHTTPError(writer, request, mediaImageReprocessUnavailable("MediaImageReprocessRun service is not configured"))
		return
	}
	run, err := handler.mediaImageReprocessService.Get(
		request.Context(),
		strings.TrimSpace(request.PathValue("runId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	writeJSON(writer, http.StatusOK, run.Snapshot())
}

func mapMediaImageReprocessError(err error) error {
	switch {
	case errors.Is(err, reprocessmodel.ErrInvalidRun):
		return mediaImageReprocessInvalidArgument(err.Error())
	case errors.Is(err, reprocessmodel.ErrInvalidRunStatus):
		return contentgenerated.AppErrorFromMediaImageReprocessInvalidTransition(err.Error())
	case errors.Is(err, reprocessmodel.ErrRunNotFound):
		return contentgenerated.AppErrorFromMediaImageReprocessRunNotFound(err.Error())
	default:
		return mediaImageReprocessUnavailable(err.Error())
	}
}

func mediaImageReprocessInvalidArgument(debugMessage string) error {
	return contentgenerated.AppErrorFromMediaImageReprocessInvalidArgument(debugMessage)
}

func mediaImageReprocessUnavailable(debugMessage string) error {
	return contentgenerated.AppErrorFromMediaImageReprocessStorageUnavailable(debugMessage)
}

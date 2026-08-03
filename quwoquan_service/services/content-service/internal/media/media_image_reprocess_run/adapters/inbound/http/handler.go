package http

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	httpcodec "quwoquan_service/runtime/httpcodec"
	mediaassetgenerated "quwoquan_service/services/content-service/generated/media/media_asset"
	contentgenerated "quwoquan_service/services/content-service/generated/media/media_image_reprocess_run"
	mediareprocessapp "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/application"
	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
)

type Handler struct{ service *mediareprocessapp.Service }

func NewHandler(service *mediareprocessapp.Service) *Handler {
	if service == nil {
		panic("MediaImageReprocessRun HTTP handler requires service")
	}
	return &Handler{service: service}
}

type startMediaImageReprocessRunBody struct {
	RunID    string   `json:"runId"`
	AssetIDs []string `json:"assetIds"`
}

func (handler *Handler) Start(
	writer http.ResponseWriter,
	request *http.Request,
) {
	var body startMediaImageReprocessRunBody
	if request.Body == nil {
		writeHTTPError(writer, request, mediaImageReprocessInvalidArgument("request body is required"))
		return
	}
	defer request.Body.Close()
	if err := json.NewDecoder(request.Body).Decode(&body); err != nil {
		writeHTTPError(writer, request, mediaImageReprocessInvalidArgument(err.Error()))
		return
	}
	run, _, err := handler.service.Start(
		request.Context(),
		mediareprocessapp.StartCommand{RunID: body.RunID, AssetIDs: body.AssetIDs},
		mediaassetgenerated.ContentImageDerivativePolicyVersion,
	)
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	httpcodec.WriteJSON(writer, http.StatusAccepted, responseFrom(run.Snapshot()), "media_image_reprocess_run")
}

func (handler *Handler) Pause(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transition(writer, request, "pause")
}

func (handler *Handler) Resume(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transition(writer, request, "resume")
}

func (handler *Handler) Rollback(
	writer http.ResponseWriter,
	request *http.Request,
) {
	handler.transition(writer, request, "rollback")
}

func (handler *Handler) transition(
	writer http.ResponseWriter,
	request *http.Request,
	operation string,
) {
	runID := strings.TrimSpace(request.PathValue("runId"))
	var (
		run *reprocessmodel.Run
		err error
	)
	switch operation {
	case "pause":
		run, _, err = handler.service.Pause(request.Context(), runID)
	case "resume":
		run, _, err = handler.service.Resume(request.Context(), runID)
	case "rollback":
		run, _, err = handler.service.StartRollback(request.Context(), runID)
	default:
		err = errors.New("unknown media image reprocess transition")
	}
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	httpcodec.WriteJSON(writer, http.StatusAccepted, responseFrom(run.Snapshot()), "media_image_reprocess_run")
}

func (handler *Handler) Get(
	writer http.ResponseWriter,
	request *http.Request,
) {
	run, err := handler.service.Get(
		request.Context(),
		strings.TrimSpace(request.PathValue("runId")),
	)
	if err != nil {
		writeHTTPError(writer, request, mapMediaImageReprocessError(err))
		return
	}
	httpcodec.WriteJSON(writer, http.StatusOK, responseFrom(run.Snapshot()), "media_image_reprocess_run")
}

type response struct {
	RunID                         string                `json:"runId"`
	Version                       int64                 `json:"version"`
	TargetDerivativePolicyVersion int                   `json:"targetDerivativePolicyVersion"`
	Status                        reprocessmodel.Status `json:"status"`
	AssetIDs                      []string              `json:"assetIds"`
	NextAssetIndex                int                   `json:"nextAssetIndex"`
	ProcessedCount                int                   `json:"processedCount"`
	FailedCount                   int                   `json:"failedCount"`
	RollbackIndex                 int                   `json:"rollbackIndex"`
	Activations                   []activationResponse  `json:"activations"`
	FailureReason                 string                `json:"failureReason,omitempty"`
	StartedAt                     time.Time             `json:"startedAt"`
	PausedAt                      *time.Time            `json:"pausedAt,omitempty"`
	CompletedAt                   *time.Time            `json:"completedAt,omitempty"`
	RolledBackAt                  *time.Time            `json:"rolledBackAt,omitempty"`
	UpdatedAt                     time.Time             `json:"updatedAt"`
}

type activationResponse struct {
	AssetID           string    `json:"assetId"`
	PreviousRevision  int       `json:"previousRevision"`
	ActivatedRevision int       `json:"activatedRevision"`
	ActivatedAt       time.Time `json:"activatedAt"`
}

func responseFrom(snapshot reprocessmodel.Snapshot) response {
	return response{
		RunID: snapshot.RunID, Version: snapshot.Version,
		TargetDerivativePolicyVersion: snapshot.TargetDerivativePolicyVersion,
		Status:                        snapshot.Status, AssetIDs: snapshot.AssetIDs,
		NextAssetIndex: snapshot.NextAssetIndex, ProcessedCount: snapshot.ProcessedCount,
		FailedCount: snapshot.FailedCount, RollbackIndex: snapshot.RollbackIndex,
		Activations: activationResponses(snapshot.Activations), FailureReason: snapshot.FailureReason,
		StartedAt: snapshot.StartedAt, PausedAt: snapshot.PausedAt,
		CompletedAt: snapshot.CompletedAt, RolledBackAt: snapshot.RolledBackAt,
		UpdatedAt: snapshot.UpdatedAt,
	}
}

func activationResponses(values []reprocessmodel.Activation) []activationResponse {
	result := make([]activationResponse, 0, len(values))
	for _, value := range values {
		result = append(result, activationResponse{
			AssetID: value.AssetID, PreviousRevision: value.PreviousRevision,
			ActivatedRevision: value.ActivatedRevision, ActivatedAt: value.ActivatedAt,
		})
	}
	return result
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

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

package http

import (
	"encoding/json"
	stdhttp "net/http"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	behaviorerrors "quwoquan_service/services/circle-service/generated/circle_management/circle_behavior_fact"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/circle_behavior_fact/domain/model"
)

type Handler struct {
	writer *app.Writer
}

func NewHandler(writer *app.Writer) *Handler {
	if writer == nil {
		panic("CircleBehaviorFact Handler requires object writer")
	}
	return &Handler{writer: writer}
}

func (handler *Handler) ServeHTTP(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	if request.Method != stdhttp.MethodPost || request.URL.Path != "/circles/behaviors" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "only POST /circles/behaviors"))
		return
	}
	var body struct {
		CircleID  string `json:"circleId"`
		EventType string `json:"eventType"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	result, err := handler.writer.Append(request.Context(), app.AppendCommand{
		CircleID: body.CircleID, EventType: model.BehaviorEventType(body.EventType),
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	payload, err := json.Marshal(result)
	if err != nil {
		writeError(writer, request, behaviorerrors.AppErrorFromBehaviorFactWriteFailed(
			"marshal CircleBehaviorFact AppendResult: "+err.Error(),
		))
		return
	}
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(stdhttp.StatusOK)
	_, _ = writer.Write(payload)
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

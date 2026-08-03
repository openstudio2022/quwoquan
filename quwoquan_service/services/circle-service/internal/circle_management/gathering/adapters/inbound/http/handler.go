package http

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	stdhttp "net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
)

type Handler struct {
	commands *app.CommandFacade
	queries  *app.QueryFacade
}

func NewHandler(commands *app.CommandFacade, queries *app.QueryFacade) *Handler {
	if commands == nil || queries == nil {
		panic("Gathering HTTP Handler requires command and query facades")
	}
	return &Handler{commands: commands, queries: queries}
}

func (handler *Handler) Register(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("Gathering HTTP Handler requires ServeMux")
	}
	mux.HandleFunc("/gatherings", handler.handleCollection)
	mux.HandleFunc("/gatherings/", handler.handleResource)
}

type createBody struct {
	Title       string           `json:"title"`
	Description string           `json:"description"`
	TargetRef   model.TargetRef  `json:"targetRef"`
	StartAt     time.Time        `json:"startAt"`
	EndAt       time.Time        `json:"endAt"`
	Capacity    int64            `json:"capacity"`
	JoinPolicy  model.JoinPolicy `json:"joinPolicy"`
}

type approveBody struct {
	ParticipantPersonaID string `json:"participantPersonaId"`
}

func (handler *Handler) handleCollection(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	if request.URL.Path != "/gatherings" || request.Method != stdhttp.MethodPost {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "Gathering collection only accepts POST"))
		return
	}
	var body createBody
	if err := readStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	result, err := handler.commands.Create(request.Context(), app.CreateCommand{
		Title: body.Title, Description: body.Description, TargetRef: body.TargetRef,
		StartAt: body.StartAt, EndAt: body.EndAt, Capacity: body.Capacity,
		JoinPolicy: body.JoinPolicy,
	})
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, stdhttp.StatusCreated, result)
}

func (handler *Handler) handleResource(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	rest := strings.TrimPrefix(request.URL.Path, "/gatherings/")
	if rest == "" || strings.Contains(rest, "/") {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "Gathering id is required"))
		return
	}
	gatheringID, action := splitAction(rest)
	if gatheringID == "" {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "Gathering id is required"))
		return
	}
	if action == "" {
		if request.Method != stdhttp.MethodGet {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "Gathering detail only accepts GET"))
			return
		}
		result, err := handler.queries.Get(request.Context(), gatheringID)
		if err != nil {
			writeError(writer, request, err)
			return
		}
		writeJSON(writer, stdhttp.StatusOK, result)
		return
	}
	if request.Method != stdhttp.MethodPost {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "Gathering action only accepts POST"))
		return
	}

	var (
		result app.CommandResult
		err    error
	)
	switch action {
	case "join":
		result, err = handler.commands.Join(request.Context(), app.GatheringCommand{GatheringID: gatheringID})
	case "approve":
		var body approveBody
		if decodeErr := readStrictJSON(request, &body); decodeErr != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", decodeErr.Error()))
			return
		}
		result, err = handler.commands.Approve(request.Context(), app.ParticipantCommand{
			GatheringID: gatheringID, ParticipantPersonaID: body.ParticipantPersonaID,
		})
	case "leave":
		result, err = handler.commands.Leave(request.Context(), app.GatheringCommand{GatheringID: gatheringID})
	case "cancel":
		result, err = handler.commands.Cancel(request.Context(), app.GatheringCommand{GatheringID: gatheringID})
	case "complete":
		result, err = handler.commands.Complete(request.Context(), app.GatheringCommand{GatheringID: gatheringID})
	default:
		err = rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown Gathering action")
	}
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, stdhttp.StatusOK, result)
}

func splitAction(raw string) (string, string) {
	parts := strings.Split(raw, ":")
	if len(parts) == 1 {
		return strings.TrimSpace(parts[0]), ""
	}
	if len(parts) != 2 {
		return "", ""
	}
	return strings.TrimSpace(parts[0]), strings.TrimSpace(parts[1])
}

func readStrictJSON(request *stdhttp.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(target); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return fmt.Errorf("request body must contain exactly one JSON object")
		}
		return err
	}
	return nil
}

func writeJSON(writer stdhttp.ResponseWriter, status int, value any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	if err := json.NewEncoder(writer).Encode(value); err != nil {
		slog.Default().Warn("Gathering response encode failed", "error", err)
	}
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

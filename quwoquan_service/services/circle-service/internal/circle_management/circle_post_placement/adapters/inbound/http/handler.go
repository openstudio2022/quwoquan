package http

import (
	stdhttp "net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/application"
)

type Handler struct {
	commands *app.CommandFacade
}

func NewHandler(commands *app.CommandFacade) *Handler {
	if commands == nil {
		panic("CirclePostPlacement Handler requires object command facade")
	}
	return &Handler{commands: commands}
}

func (handler *Handler) ServeCircleRoute(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	circleID string,
	rest []string,
) {
	if len(rest) == 0 {
		if request.Method != stdhttp.MethodPost {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "post-placements collection only accepts POST"))
			return
		}
		var body struct {
			PostID  string `json:"postId"`
			GroupID string `json:"groupId"`
		}
		if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.commands.Place(request.Context(), app.PlaceCommand{
			CircleID: circleID, PostID: body.PostID, GroupID: body.GroupID,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "circle_post_placement")
		return
	}

	placementID := strings.TrimSpace(rest[0])
	if len(rest) == 1 {
		if request.Method != stdhttp.MethodDelete {
			writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "placement resource only accepts DELETE"))
			return
		}
		result, err := handler.commands.Remove(request.Context(), app.TargetCommand{
			CircleID: circleID, PlacementID: placementID,
		})
		if err != nil {
			writeError(writer, request, err)
			return
		}
		httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_post_placement")
		return
	}
	if len(rest) != 2 || request.Method != stdhttp.MethodPatch || (rest[1] != "pin" && rest[1] != "feature") {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown post placement command"))
		return
	}
	var body struct {
		Enabled bool `json:"enabled"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		writeError(writer, request, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	command := app.PresentationCommand{CircleID: circleID, PlacementID: placementID, Enabled: body.Enabled}
	var (
		result app.CommandResult
		err    error
	)
	if rest[1] == "pin" {
		result, err = handler.commands.SetPinned(request.Context(), command)
	} else {
		result, err = handler.commands.SetFeatured(request.Context(), command)
	}
	if err != nil {
		writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "circle_post_placement")
}

func writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

package http

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	placementapp "quwoquan_service/services/circle-service/internal/application/circle/circle_post_placement"
)

func (handler *CircleHandler) handlePostPlacements(w http.ResponseWriter, r *http.Request, circleID string, rest []string) {
	if len(rest) == 0 {
		if r.Method != http.MethodPost {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "post-placements collection only accepts POST"))
			return
		}
		var body struct {
			PostID  string `json:"postId"`
			GroupID string `json:"groupId"`
		}
		if err := readStrictJSON(r, &body); err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
			return
		}
		result, err := handler.placementCommands.Place(r.Context(), placementapp.PlaceCommand{
			CircleID: circleID, PostID: body.PostID, GroupID: body.GroupID,
		})
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusCreated, result)
		return
	}

	placementID := strings.TrimSpace(rest[0])
	if len(rest) == 1 {
		if r.Method != http.MethodDelete {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "方法不支持", "placement resource only accepts DELETE"))
			return
		}
		expectedVersion, err := parseExpectedVersion(r.Header.Get("If-Match"))
		if err != nil {
			writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求缺少有效版本", err.Error()))
			return
		}
		result, err := handler.placementCommands.Remove(r.Context(), placementapp.VersionedCommand{
			CircleID: circleID, PlacementID: placementID, ExpectedVersion: expectedVersion,
		})
		if err != nil {
			writeHTTPError(w, r, err)
			return
		}
		writeJSON(w, http.StatusOK, result)
		return
	}
	if len(rest) != 2 || r.Method != http.MethodPatch || (rest[1] != "pin" && rest[1] != "feature") {
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "unknown post placement command"))
		return
	}
	var body struct {
		Enabled         bool  `json:"enabled"`
		ExpectedVersion int64 `json:"expectedVersion"`
	}
	if err := readStrictJSON(r, &body); err != nil || body.ExpectedVersion <= 0 {
		if err == nil {
			err = fmt.Errorf("expectedVersion must be positive")
		}
		writeHTTPError(w, r, rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()))
		return
	}
	command := placementapp.PresentationCommand{
		CircleID: circleID, PlacementID: placementID,
		ExpectedVersion: body.ExpectedVersion, Enabled: body.Enabled,
	}
	var (
		result placementapp.CommandResult
		err    error
	)
	if rest[1] == "pin" {
		result, err = handler.placementCommands.SetPinned(r.Context(), command)
	} else {
		result, err = handler.placementCommands.SetFeatured(r.Context(), command)
	}
	if err != nil {
		writeHTTPError(w, r, err)
		return
	}
	writeJSON(w, http.StatusOK, result)
}

func readStrictJSON(r *http.Request, target any) error {
	decoder := json.NewDecoder(io.LimitReader(r.Body, 1<<20))
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

func parseExpectedVersion(raw string) (int64, error) {
	normalized := strings.TrimSpace(raw)
	normalized = strings.TrimPrefix(normalized, "W/")
	normalized = strings.Trim(normalized, "\"")
	value, err := strconv.ParseInt(normalized, 10, 64)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("If-Match must contain a positive aggregate version")
	}
	return value, nil
}

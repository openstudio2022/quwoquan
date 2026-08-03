package http

import (
	"io"
	"net/http"
	"strconv"
	"strings"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	intersectionapp "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application"
	intersectionquery "quwoquan_service/services/content-service/internal/content/intersection_visit_state/application/intersection"
	intersectionmodel "quwoquan_service/services/content-service/internal/content/intersection_visit_state/domain/model"
)

type Handler struct {
	commands *intersectionapp.Commands
	queries  *intersectionquery.IntersectionService
}

func NewHandler(
	commands *intersectionapp.Commands,
	queries *intersectionquery.IntersectionService,
) *Handler {
	if commands == nil {
		panic("IntersectionVisitState HTTP handler requires command facade")
	}
	if queries == nil {
		panic("IntersectionVisitState HTTP handler requires query facade")
	}
	return &Handler{commands: commands, queries: queries}
}

type markRequest struct {
	Dimension string `json:"dimension"`
}

type markAck struct {
	Dimensions []string `json:"dimensions"`
	Status     string   `json:"status"`
}

func (handler *Handler) MarkVisited(writer http.ResponseWriter, request *http.Request) {
	personaID, ok := personaIDFromRequest(request)
	if !ok {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"missing persona",
		))
		return
	}
	var body markRequest
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil && err != io.EOF {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"请求体解析失败",
			err.Error(),
		))
		return
	}
	dimension := strings.TrimSpace(body.Dimension)
	if err := handler.commands.MarkVisited(
		request.Context(),
		personaID,
		dimension,
	); err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	dimensions := append([]string(nil), intersectionmodel.Dimensions...)
	if dimension != "" {
		dimensions = []string{dimension}
	}
	httpcodec.WriteJSON(writer, http.StatusOK, markAck{
		Dimensions: dimensions,
		Status:     "visited",
	}, "intersection_visit_state")
}

type intersectionReasonPage struct {
	Items      []intersectionquery.IntersectionReasonView `json:"items"`
	Dimension  string                                     `json:"dimension,omitempty"`
	NextCursor string                                     `json:"nextCursor,omitempty"`
	HasMore    bool                                       `json:"hasMore"`
}

type objectIntersectionReasonSlice struct {
	Items      []intersectionquery.IntersectionReasonView `json:"items"`
	ObjectID   string                                     `json:"objectId"`
	ObjectType string                                     `json:"objectType"`
}

func (handler *Handler) GetMyIntersectionSummary(writer http.ResponseWriter, request *http.Request) {
	personaID, ok := personaIDFromRequest(request)
	if !ok {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"missing persona",
		))
		return
	}
	summary, err := handler.queries.Summary(request.Context(), personaID)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, http.StatusOK, summary, "intersection_visit_state")
}

func (handler *Handler) ListMyIntersections(writer http.ResponseWriter, request *http.Request) {
	personaID, ok := personaIDFromRequest(request)
	if !ok {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"missing persona",
		))
		return
	}
	query := request.URL.Query()
	limit, err := positiveLimit(query.Get("limit"), 50)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	dimension := strings.TrimSpace(query.Get("dimension"))
	items, nextCursor, hasMore, err := handler.queries.List(
		request.Context(),
		personaID,
		intersectionquery.IntersectionListQuery{
			Dimension:  dimension,
			Filter:     strings.TrimSpace(query.Get("filter")),
			SourceRef:  strings.TrimSpace(query.Get("sourceRef")),
			TimeBucket: strings.TrimSpace(query.Get("timeBucket")),
			Cursor:     strings.TrimSpace(query.Get("cursor")),
			Limit:      limit,
		},
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, http.StatusOK, intersectionReasonPage{
		Items:      items,
		Dimension:  dimension,
		NextCursor: nextCursor,
		HasMore:    hasMore,
	}, "intersection_visit_state")
}

func (handler *Handler) GetObjectIntersections(writer http.ResponseWriter, request *http.Request) {
	personaID, ok := personaIDFromRequest(request)
	if !ok {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"需要登录",
			"missing persona",
		))
		return
	}
	query := request.URL.Query()
	objectID := strings.TrimSpace(query.Get("objectId"))
	if objectID == "" {
		writeHTTPError(writer, request, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"缺少对象",
			"missing objectId",
		))
		return
	}
	limit, err := positiveLimit(query.Get("limit"), 8)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	objectType := strings.TrimSpace(query.Get("objectType"))
	items, err := handler.queries.ObjectIntersections(
		request.Context(),
		personaID,
		objectID,
		objectType,
		limit,
	)
	if err != nil {
		writeHTTPError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, http.StatusOK, objectIntersectionReasonSlice{
		Items:      items,
		ObjectID:   objectID,
		ObjectType: objectType,
	}, "intersection_visit_state")
}

func personaIDFromRequest(request *http.Request) (string, bool) {
	principal, ok := rtauth.PrincipalFromContext(request.Context())
	if !ok {
		return "", false
	}
	personaID := strings.TrimSpace(principal.Actor.PersonaID)
	return personaID, personaID != ""
}

func positiveLimit(raw string, fallback int) (int, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"分页数量无效",
			"limit must be a positive integer",
		)
	}
	return value, nil
}

func writeHTTPError(writer http.ResponseWriter, request *http.Request, err error) {
	rterr.WriteHTTPError(writer, err, rterr.HTTPWriteOptionsFromRequest(request))
}

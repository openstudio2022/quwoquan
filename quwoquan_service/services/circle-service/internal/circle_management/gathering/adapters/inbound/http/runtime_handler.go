package http

import (
	stdhttp "net/http"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

// Handler is the single generated Gathering route dispatcher. Go ServeMux
// cannot express a wildcard followed by a literal ":action" suffix, so all
// command scopes share one method-aware resource pattern.
type Handler struct {
	lifecycle     *LifecycleHandler
	participation *ParticipationHandler
	hostOutcome   *HostOutcomeHandler
	queries       *QueryHandler
}

func NewHandler(
	lifecycle *app.LifecycleFacade,
	participation *app.CommandFacade,
	hostOutcome *app.HostOutcomeFacade,
	queries *app.GatheringQueryFacade,
) *Handler {
	if lifecycle == nil || participation == nil || hostOutcome == nil ||
		queries == nil {
		panic("Gathering Handler requires lifecycle, participation, host/outcome and query facades")
	}
	return &Handler{
		lifecycle:     NewLifecycleHandler(lifecycle),
		participation: NewParticipationHandler(participation),
		hostOutcome:   NewHostOutcomeHandler(hostOutcome),
		queries:       NewQueryHandler(queries),
	}
}

func (handler *Handler) Register(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("Gathering Handler requires ServeMux")
	}
	mux.HandleFunc("POST /gatherings", handler.lifecycle.handleLifecycleCollection)
	mux.HandleFunc("PUT /gatherings/{resource}", handler.lifecycle.handleLifecycleResource)
	mux.HandleFunc("POST /gatherings/{resource}", handler.dispatchAction)
	handler.queries.Register(mux)
}

func (handler *Handler) dispatchAction(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
) {
	resource := strings.TrimSpace(request.PathValue("resource"))
	gatheringID, action := splitAction(resource)
	if gatheringID == "" || action == "" {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleCircle,
				"无效路径",
				"Gathering action path requires gatheringId and action",
			),
		)
		return
	}
	request.SetPathValue("gatheringId", gatheringID)
	switch {
	case IsLifecycleAction(action):
		handler.lifecycle.handleLifecycleResource(writer, request)
	case IsParticipationAction(action):
		handler.participation.handleParticipationAction(
			writer,
			request,
			gatheringID,
			action,
		)
	default:
		resolved, ok := handler.hostOutcome.ResolveAction(action)
		if !ok {
			writeError(
				writer,
				request,
				rterr.NewInvalidArgument(
					rterr.ModuleCircle,
					"无效路径",
					"unknown Gathering action",
				),
			)
			return
		}
		resolved(writer, request)
	}
}

// IsLifecycleAction reports whether the shared Gathering dispatcher routes the
// action to the lifecycle facade. The adapter package is internal to the
// service; exporting this classifier lets object-local contract tests verify
// the production routing table without duplicating it.
func IsLifecycleAction(action string) bool {
	switch strings.TrimSpace(action) {
	case "publish", "cancel", "complete", "end-early", "safety-terminate":
		return true
	default:
		return false
	}
}

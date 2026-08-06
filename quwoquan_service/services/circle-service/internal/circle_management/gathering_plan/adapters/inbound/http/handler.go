package http

import (
	stdhttp "net/http"
	"strconv"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/httpcodec"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
)

type Handler struct {
	commands *app.GatheringPlanCommandFacet
	queries  *app.GatheringPlanQueryFacet
	mapError func(error) error
}

func NewHandler(commands *app.GatheringPlanCommandFacet, queries *app.GatheringPlanQueryFacet, mapError func(error) error) *Handler {
	if commands == nil || queries == nil || mapError == nil {
		panic("GatheringPlan Handler requires command/query facets and canonical error mapper")
	}
	return &Handler{commands: commands, queries: queries, mapError: mapError}
}

func (handler *Handler) Register(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("GatheringPlan Handler requires ServeMux")
	}
	mux.HandleFunc("POST /gatherings/{gatheringId}/plan", handler.create)
	mux.HandleFunc("POST /gathering-plans/{planId}/proposals", handler.propose)
	mux.HandleFunc("POST /gathering-plans/{planId}/commit", handler.commit)
	mux.HandleFunc("GET /gatherings/{gatheringId}/plan", handler.get)
	mux.HandleFunc("GET /gathering-plans/{planId}/revisions", handler.listRevisions)
}

func (handler *Handler) writeError(writer stdhttp.ResponseWriter, request *stdhttp.Request, err error) {
	rterr.WriteHTTPError(writer, handler.mapError(err), rterr.HTTPWriteOptionsFromRequest(request))
}

func (handler *Handler) create(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		Items                     []model.PlanItem            `json:"items"`
		AcknowledgementPolicy     model.AcknowledgementPolicy `json:"acknowledgementPolicy"`
		AffectedParticipationRefs []model.ParticipationRef    `json:"affectedParticipationRefs"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		handler.writeError(writer, request, model.ErrInvalid)
		return
	}
	result, err := handler.commands.CreateGatheringPlan(request.Context(), app.CreateGatheringPlanCommand{
		GatheringID: request.PathValue("gatheringId"), Items: body.Items,
		AcknowledgementPolicy:     body.AcknowledgementPolicy,
		AffectedParticipationRefs: body.AffectedParticipationRefs,
	})
	if err != nil {
		handler.writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusCreated, result, "gathering_plan")
}

func (handler *Handler) propose(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		ExpectedPlanVersion       int64                       `json:"expectedPlanVersion"`
		BaseRevisionID            string                      `json:"baseRevisionId"`
		BaseRevisionNumber        int                         `json:"baseRevisionNumber"`
		BaseRevisionDigest        string                      `json:"baseRevisionDigest"`
		Items                     []model.PlanItem            `json:"items"`
		AcknowledgementPolicy     model.AcknowledgementPolicy `json:"acknowledgementPolicy"`
		AffectedParticipationRefs []model.ParticipationRef    `json:"affectedParticipationRefs"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		handler.writeError(writer, request, model.ErrInvalid)
		return
	}
	result, err := handler.commands.ProposeGatheringPlan(request.Context(), app.ProposeGatheringPlanCommand{
		PlanID: request.PathValue("planId"), ExpectedPlanVersion: body.ExpectedPlanVersion,
		BaseRevisionID: body.BaseRevisionID, BaseRevisionNumber: body.BaseRevisionNumber,
		BaseRevisionDigest: body.BaseRevisionDigest, Items: body.Items,
		AcknowledgementPolicy:     body.AcknowledgementPolicy,
		AffectedParticipationRefs: body.AffectedParticipationRefs,
	})
	if err != nil {
		handler.writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "gathering_plan")
}

func (handler *Handler) commit(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	var body struct {
		ProposalID                 string `json:"proposalId"`
		ExpectedPlanVersion        int64  `json:"expectedPlanVersion"`
		ExpectedProposalDigest     string `json:"expectedProposalDigest"`
		ExpectedBaseRevisionDigest string `json:"expectedBaseRevisionDigest"`
	}
	if err := httpcodec.DecodeStrictJSON(request, &body); err != nil {
		handler.writeError(writer, request, model.ErrInvalid)
		return
	}
	result, err := handler.commands.CommitGatheringPlanProposal(request.Context(), app.CommitGatheringPlanProposalCommand{
		PlanID: request.PathValue("planId"), ProposalID: body.ProposalID,
		ExpectedPlanVersion:        body.ExpectedPlanVersion,
		ExpectedProposalDigest:     body.ExpectedProposalDigest,
		ExpectedBaseRevisionDigest: body.ExpectedBaseRevisionDigest,
	})
	if err != nil {
		handler.writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "gathering_plan")
}

func (handler *Handler) get(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	result, err := handler.queries.GetGatheringPlan(request.Context(), request.PathValue("gatheringId"))
	if err != nil {
		handler.writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "gathering_plan")
}

func (handler *Handler) listRevisions(writer stdhttp.ResponseWriter, request *stdhttp.Request) {
	limit := 0
	if raw := strings.TrimSpace(request.URL.Query().Get("limit")); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed <= 0 {
			handler.writeError(writer, request, model.ErrCursorInvalid)
			return
		}
		limit = parsed
	}
	result, err := handler.queries.ListGatheringPlanRevisions(
		request.Context(), request.PathValue("planId"), request.URL.Query().Get("cursor"), limit,
	)
	if err != nil {
		handler.writeError(writer, request, err)
		return
	}
	httpcodec.WriteJSON(writer, stdhttp.StatusOK, result, "gathering_plan_revision_page")
}

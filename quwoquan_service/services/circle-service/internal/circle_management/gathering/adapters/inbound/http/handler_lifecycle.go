package http

import (
	stdhttp "net/http"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

type LifecycleHandler struct {
	facade *app.LifecycleFacade
}

func NewLifecycleHandler(facade *app.LifecycleFacade) *LifecycleHandler {
	if facade == nil {
		panic("Gathering LifecycleHandler requires LifecycleFacade")
	}
	return &LifecycleHandler{facade: facade}
}

// Register owns only exact method-aware lifecycle patterns. Composition must
// not also register legacy/Scope C handlers for complete or end-early.
func (handler *LifecycleHandler) Register(mux *stdhttp.ServeMux) {
	if mux == nil {
		panic("Gathering LifecycleHandler requires ServeMux")
	}
	mux.HandleFunc("POST /gatherings", handler.handleLifecycleCollection)
	mux.HandleFunc("PUT /gatherings/{resource}", handler.handleLifecycleResource)
	mux.HandleFunc("POST /gatherings/{resource}", handler.handleLifecycleResource)
}

type createGatheringDraftBody struct {
	HostBinding         contract.HostBinding        `json:"hostBinding"`
	CreatorParticipates bool                        `json:"creatorParticipates"`
	Purpose             contract.GatheringPurpose   `json:"purpose"`
	Schedule            contract.GatheringSchedule  `json:"schedule"`
	Place               contract.GatheringPlace     `json:"place"`
	PolicySet           contract.GatheringPolicySet `json:"policySet"`
}

type gatheringVersionBody struct {
	ExpectedGatheringVersion int64 `json:"expectedGatheringVersion"`
}

type updateGatheringBody struct {
	ExpectedGatheringVersion  int64                       `json:"expectedGatheringVersion"`
	Purpose                   contract.GatheringPurpose   `json:"purpose"`
	Schedule                  contract.GatheringSchedule  `json:"schedule"`
	Place                     contract.GatheringPlace     `json:"place"`
	PolicySet                 contract.GatheringPolicySet `json:"policySet"`
	HostBinding               contract.HostBinding        `json:"hostBinding"`
	AcknowledgementDeadlineAt time.Time                   `json:"acknowledgementDeadlineAt"`
}

type gatheringReasonBody struct {
	ExpectedGatheringVersion int64                         `json:"expectedGatheringVersion"`
	ReasonRef                string                        `json:"reasonRef"`
	EvidenceRefs             []contract.CanonicalObjectRef `json:"evidenceRefs"`
}

func (handler *LifecycleHandler) handleLifecycleCollection(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
) {
	if request.URL.Path != "/gatherings" || request.Method != stdhttp.MethodPost {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleCircle,
				"方法不支持",
				"Gathering lifecycle collection only accepts POST",
			),
		)
		return
	}
	var body createGatheringDraftBody
	if err := readStrictJSON(request, &body); err != nil {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()),
		)
		return
	}
	result, err := handler.facade.CreateGatheringDraft(
		request.Context(),
		app.CreateGatheringDraftCommand{
			HostBinding:         body.HostBinding,
			CreatorParticipates: body.CreatorParticipates,
			Purpose:             body.Purpose,
			Schedule:            body.Schedule,
			Place:               body.Place,
			PolicySet:           body.PolicySet,
		},
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, stdhttp.StatusCreated, result)
}

func (handler *LifecycleHandler) handleLifecycleResource(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
) {
	rest := strings.TrimPrefix(request.URL.Path, "/gatherings/")
	if rest == "" || strings.Contains(rest, "/") {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "Gathering id is required"),
		)
		return
	}
	gatheringID, action := splitAction(rest)
	if strings.TrimSpace(gatheringID) == "" {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "无效路径", "Gathering id is required"),
		)
		return
	}
	if action == "" {
		handler.handleLifecycleUpdate(writer, request, gatheringID)
		return
	}
	if request.Method != stdhttp.MethodPost {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleCircle,
				"方法不支持",
				"Gathering lifecycle action only accepts POST",
			),
		)
		return
	}

	var (
		result app.LifecycleCommandResult
		err    error
	)
	switch action {
	case "publish", "complete":
		var body gatheringVersionBody
		if decodeErr := readStrictJSON(request, &body); decodeErr != nil {
			writeError(
				writer,
				request,
				rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", decodeErr.Error()),
			)
			return
		}
		command := app.GatheringVersionCommand{
			GatheringID:              gatheringID,
			ExpectedGatheringVersion: body.ExpectedGatheringVersion,
		}
		if action == "publish" {
			result, err = handler.facade.PublishGathering(request.Context(), command)
		} else {
			result, err = handler.facade.CompleteGathering(request.Context(), command)
		}
	case "cancel", "end-early", "safety-terminate":
		var body gatheringReasonBody
		if decodeErr := readStrictJSON(request, &body); decodeErr != nil {
			writeError(
				writer,
				request,
				rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", decodeErr.Error()),
			)
			return
		}
		command := app.GatheringReasonCommand{
			GatheringID:              gatheringID,
			ExpectedGatheringVersion: body.ExpectedGatheringVersion,
			ReasonRef:                body.ReasonRef,
			EvidenceRefs:             body.EvidenceRefs,
		}
		switch action {
		case "cancel":
			result, err = handler.facade.CancelGathering(request.Context(), command)
		case "end-early":
			result, err = handler.facade.EndGatheringEarly(request.Context(), command)
		default:
			result, err = handler.facade.SafetyTerminateGathering(request.Context(), command)
		}
	default:
		err = rterr.NewInvalidArgument(
			rterr.ModuleCircle,
			"无效路径",
			"unknown Gathering lifecycle action",
		)
	}
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, stdhttp.StatusOK, result)
}

func (handler *LifecycleHandler) handleLifecycleUpdate(
	writer stdhttp.ResponseWriter,
	request *stdhttp.Request,
	gatheringID string,
) {
	if request.Method != stdhttp.MethodPut {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(
				rterr.ModuleCircle,
				"方法不支持",
				"Gathering lifecycle resource only accepts PUT",
			),
		)
		return
	}
	var body updateGatheringBody
	if err := readStrictJSON(request, &body); err != nil {
		writeError(
			writer,
			request,
			rterr.NewInvalidArgument(rterr.ModuleCircle, "请求体无效", err.Error()),
		)
		return
	}
	result, err := handler.facade.UpdateGathering(
		request.Context(),
		app.UpdateGatheringCommand{
			GatheringID:               gatheringID,
			ExpectedGatheringVersion:  body.ExpectedGatheringVersion,
			Purpose:                   body.Purpose,
			Schedule:                  body.Schedule,
			Place:                     body.Place,
			PolicySet:                 body.PolicySet,
			HostBinding:               body.HostBinding,
			AcknowledgementDeadlineAt: body.AcknowledgementDeadlineAt,
		},
	)
	if err != nil {
		writeError(writer, request, err)
		return
	}
	writeJSON(writer, stdhttp.StatusOK, result)
}

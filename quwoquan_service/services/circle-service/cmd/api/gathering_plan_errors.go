package main

import (
	"errors"

	planerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering_plan"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
)

// mapGatheringPlanError is composed beside generated errors so the object HTTP
// adapter remains independently testable without copying errors.yaml transport
// semantics into handwritten code.
func mapGatheringPlanError(err error) error {
	switch {
	case errors.Is(err, model.ErrInvalid):
		return planerrors.AppErrorFromGatheringPlanInvalid(err.Error())
	case errors.Is(err, model.ErrCursorInvalid):
		return planerrors.AppErrorFromGatheringPlanCursorInvalid(err.Error())
	case errors.Is(err, model.ErrNotFound):
		return planerrors.AppErrorFromGatheringPlanNotFound(err.Error())
	case errors.Is(err, model.ErrProposalNotFound):
		return planerrors.AppErrorFromGatheringPlanProposalNotFound(err.Error())
	case errors.Is(err, model.ErrAlreadyExists):
		return planerrors.AppErrorFromGatheringPlanAlreadyExists(err.Error())
	case errors.Is(err, model.ErrPermissionDenied):
		return planerrors.AppErrorFromGatheringPlanPermissionDenied(err.Error())
	case errors.Is(err, model.ErrGatheringUnavailable):
		return planerrors.AppErrorFromGatheringPlanGatheringUnavailable(err.Error())
	case errors.Is(err, model.ErrVersionConflict):
		return planerrors.AppErrorFromGatheringPlanVersionConflict(err.Error())
	case errors.Is(err, model.ErrRevisionConflict):
		return planerrors.AppErrorFromGatheringPlanRevisionConflict(err.Error())
	case errors.Is(err, model.ErrProposalConflict):
		return planerrors.AppErrorFromGatheringPlanProposalConflict(err.Error())
	case errors.Is(err, model.ErrIdempotencyConflict):
		return planerrors.AppErrorFromGatheringPlanIdempotencyConflict(err.Error())
	default:
		return planerrors.AppErrorFromGatheringPlanStorageFailed(err.Error())
	}
}

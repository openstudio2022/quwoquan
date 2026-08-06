package gatheringplan

import "errors"

var (
	ErrInvalid              = errors.New("GatheringPlan invalid")
	ErrNotFound             = errors.New("GatheringPlan not found")
	ErrProposalNotFound     = errors.New("GatheringPlan proposal not found")
	ErrAlreadyExists        = errors.New("GatheringPlan already exists")
	ErrPermissionDenied     = errors.New("GatheringPlan permission denied")
	ErrGatheringUnavailable = errors.New("Gathering unavailable for GatheringPlan")
	ErrVersionConflict      = errors.New("GatheringPlan version conflict")
	ErrRevisionConflict     = errors.New("GatheringPlan revision conflict")
	ErrProposalConflict     = errors.New("GatheringPlan proposal conflict")
	ErrIdempotencyConflict  = errors.New("GatheringPlan idempotency conflict")
	ErrCursorInvalid        = errors.New("GatheringPlan cursor invalid")
)

package model

import "errors"

var (
	ErrInvalidArgument     = errors.New("filter catalog invalid argument")
	ErrDigestMismatch      = errors.New("filter catalog digest mismatch")
	ErrReleaseNotFound     = errors.New("filter catalog release not found")
	ErrInvalidTransition   = errors.New("filter catalog invalid transition")
	ErrIdempotencyConflict = errors.New("filter catalog idempotency conflict")
	ErrVersionConflict     = errors.New("filter catalog version conflict")
	ErrCatalogUnavailable  = errors.New("active filter catalog unavailable")
	ErrStorageUnavailable  = errors.New("filter catalog storage unavailable")
)

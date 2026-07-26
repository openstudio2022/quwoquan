package model

import "errors"

var (
	ErrNotFound            = errors.New("persona not found")
	ErrRetired             = errors.New("persona is retired")
	ErrInvalidArgument     = errors.New("persona command is invalid")
	ErrVersionConflict     = errors.New("persona version conflict")
	ErrIdempotencyConflict = errors.New("persona idempotency conflict")
)

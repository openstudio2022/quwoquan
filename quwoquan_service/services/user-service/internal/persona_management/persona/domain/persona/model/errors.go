package model

import "errors"

var (
	ErrInvalidArgument = errors.New("persona command is invalid")
	ErrNotFound        = errors.New("persona not found")
	ErrRetired         = errors.New("persona is retired")
)

package ports

import (
	"context"
	"time"
)

type VisibilityStore interface {
	HiddenBefore(context.Context, string, string) (*time.Time, error)
	HideBefore(context.Context, string, string, time.Time) error
}

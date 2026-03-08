package persistence

import (
	"context"

	"quwoquan_service/services/rtc-service/internal/domain/call_session/model"
)

// CallRepository defines the storage operations used by the application layer.
type CallRepository interface {
	CreateCall(ctx context.Context, session *model.CallSession) error
	FindCallByID(ctx context.Context, id string) (*model.CallSession, error)
	UpdateCall(ctx context.Context, session *model.CallSession) error
	DeleteCall(ctx context.Context, id string) error
	ListCallsByUserID(ctx context.Context, userID string, limit int, cursor string) ([]*model.CallSession, error)
	FindActiveCallByUserID(ctx context.Context, userID string) (*model.CallSession, error)
}

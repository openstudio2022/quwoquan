// Package ports 定义 TagFeedback 的 typed append sink 端口。
package ports

import (
	"context"

	"quwoquan_service/services/tag-service/internal/domain/tagfeedback/model"
)

// Sink 只允许追加与 dedupe：同 (actorId, idempotencyKey) 重放安全返回已有事实。
type Sink interface {
	Append(ctx context.Context, feedback model.Feedback) (model.Feedback, bool, error)
}

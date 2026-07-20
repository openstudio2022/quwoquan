package command

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	shareports "quwoquan_service/services/content-service/internal/domain/content/outbound_share_fact/ports"
)

const outboundShareRecordedEventType = "OutboundShareRecorded"

// ShareCountReader 返回 OutboundShareFact 的权威去重计数。
// projector 每次从事实集合重算，outbox 重放不会造成 $inc 双计。
type ShareCountReader interface {
	CountByPost(ctx context.Context, postID string) (int64, error)
}

type ShareCountProjectionWriter interface {
	SetShareCount(ctx context.Context, postID string, count int64) (bool, error)
}

type ShareCountProjector struct {
	counts ShareCountReader
	writer ShareCountProjectionWriter
}

func NewShareCountProjector(
	counts ShareCountReader,
	writer ShareCountProjectionWriter,
) *ShareCountProjector {
	return &ShareCountProjector{counts: counts, writer: writer}
}

func (p *ShareCountProjector) Publish(
	ctx context.Context,
	event shareports.OutboxEvent,
) error {
	if p == nil || p.counts == nil || p.writer == nil {
		return fmt.Errorf("OutboundShareFact count projector is not configured")
	}
	if event.EventType != outboundShareRecordedEventType {
		return nil
	}
	var payload struct {
		PostID string `json:"postId"`
	}
	if err := json.Unmarshal(event.Payload, &payload); err != nil {
		return fmt.Errorf("decode OutboundShareRecorded count event: %w", err)
	}
	postID := strings.TrimSpace(payload.PostID)
	if postID == "" {
		return fmt.Errorf("OutboundShareRecorded count event has no postId")
	}
	count, err := p.counts.CountByPost(ctx, postID)
	if err != nil {
		return fmt.Errorf("count OutboundShareFact projection: %w", err)
	}
	updated, err := p.writer.SetShareCount(ctx, postID, count)
	if err != nil {
		return fmt.Errorf("write Post share count projection: %w", err)
	}
	if !updated {
		return fmt.Errorf("Post share count target %q is missing", postID)
	}
	return nil
}

var _ shareports.OutboxPublisher = (*ShareCountProjector)(nil)

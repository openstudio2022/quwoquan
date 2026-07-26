package messaging

import (
	"context"
	"fmt"
	"strings"
	"time"

	rtredis "quwoquan_service/runtime/redis"
	reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"
)

const ReportNotificationStream = "events.content.report_lifecycle"

// ReportNotificationStreamPublisher 把举报结案事实投递到 durable stream。
// Report 聚合 outbox checkpoint 与通知消费者 group 各自保证至少一次重放；
// Notification 的 idempotencyKey 再把重复事实收敛为一条 AppMessage。
type ReportNotificationStreamPublisher struct {
	redis rtredis.Client
}

func NewReportNotificationStreamPublisher(
	redis rtredis.Client,
) *ReportNotificationStreamPublisher {
	return &ReportNotificationStreamPublisher{redis: redis}
}

func (p *ReportNotificationStreamPublisher) Publish(
	ctx context.Context,
	event reportports.OutboxEvent,
) error {
	if event.EventType != "content.report.resolved" &&
		event.EventType != "content.report.dismissed" {
		return nil
	}
	if p == nil || p.redis == nil {
		return fmt.Errorf("report notification stream publisher is not configured")
	}
	eventID := strings.TrimSpace(event.EventID)
	if eventID == "" {
		return fmt.Errorf("report notification event has no stable event id")
	}
	_, err := p.redis.XAdd(ctx, ReportNotificationStream, map[string]string{
		"eventId":     eventID,
		"eventType":   event.EventType,
		"aggregateId": strings.TrimSpace(event.AggregateID),
		"payload":     string(event.Payload),
		"occurredAt":  event.OccurredAt.UTC().Format(time.RFC3339Nano),
	})
	if err != nil {
		return fmt.Errorf("append report notification stream: %w", err)
	}
	return nil
}

var _ reportports.OutboxPublisher = (*ReportNotificationStreamPublisher)(nil)

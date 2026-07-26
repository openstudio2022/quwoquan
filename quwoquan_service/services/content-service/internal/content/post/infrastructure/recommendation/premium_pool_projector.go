package recommendation

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
)

const (
	PremiumPoolEntryUpsertedEvent        = "PremiumPoolEntryUpserted"
	PremiumPoolEntryRolledBackEvent      = "PremiumPoolEntryRolledBack"
	PremiumPoolEntryTakedownEjectedEvent = "PremiumPoolEntryTakedownEjected"

	PremiumPoolEntryUpsertedChannel        = "events.ops." + PremiumPoolEntryUpsertedEvent
	PremiumPoolEntryRolledBackChannel      = "events.ops." + PremiumPoolEntryRolledBackEvent
	PremiumPoolEntryTakedownEjectedChannel = "events.ops." + PremiumPoolEntryTakedownEjectedEvent
)

type premiumPoolProjectionWriter interface {
	UpsertPremiumProjection(ctx context.Context, fields bson.M) error
	MarkPremiumProjectionTakedown(ctx context.Context, contentID string, now time.Time) error
}

// PremiumPoolProjector owns the content-service recommendation read projection
// for product-ops global premium entries. It is intentionally separate from
// product-ops control state; feed reads only consume rm_premium_pool.
type PremiumPoolProjector struct {
	writer premiumPoolProjectionWriter
	now    func() time.Time
}

func NewPremiumPoolProjector(db *mongo.Database) *PremiumPoolProjector {
	return NewPremiumPoolProjectorWithWriter(mongoPremiumPoolProjectionWriter{
		coll: db.Collection("rm_premium_pool"),
	})
}

func NewPremiumPoolProjectorWithWriter(writer premiumPoolProjectionWriter) *PremiumPoolProjector {
	return &PremiumPoolProjector{
		writer: writer,
		now:    func() time.Time { return time.Now().UTC() },
	}
}

func (p *PremiumPoolProjector) SetNow(now func() time.Time) {
	if p == nil || now == nil {
		return
	}
	p.now = now
}

func (p *PremiumPoolProjector) EventTypes() []string {
	return []string{
		PremiumPoolEntryUpsertedEvent,
		PremiumPoolEntryRolledBackEvent,
		PremiumPoolEntryTakedownEjectedEvent,
		"PostDeleted",
		"PostTakedown",
	}
}

func (p *PremiumPoolProjector) Project(ctx context.Context, event ProjectorEvent) error {
	if p == nil || p.writer == nil {
		return nil
	}
	switch strings.TrimSpace(event.Type) {
	case PremiumPoolEntryUpsertedEvent, PremiumPoolEntryRolledBackEvent, PremiumPoolEntryTakedownEjectedEvent:
		input := premiumPoolProjectionInputFromPayload(event.Payload, event.OccurredAt)
		fields := BuildPremiumPoolProjectionFields(input, p.now())
		return p.writer.UpsertPremiumProjection(ctx, fields)
	case "PostDeleted", "PostTakedown":
		contentID := firstNonEmpty(
			StrVal(event.Payload, "postId"),
			StrVal(event.Payload, "contentId"),
			event.AggregateID,
		)
		if contentID == "" {
			return nil
		}
		return p.writer.MarkPremiumProjectionTakedown(ctx, contentID, p.now())
	default:
		return nil
	}
}

func premiumPoolProjectionInputFromPayload(payload map[string]any, occurredAt time.Time) PremiumPoolProjectionInput {
	return PremiumPoolProjectionInput{
		ContentID:        StrVal(payload, "contentId"),
		Scope:            StrVal(payload, "scope"),
		Status:           StrVal(payload, "status"),
		QualityAdmission: StrVal(payload, "qualityAdmission"),
		QualityScore:     premiumPoolFloat(payload["qualityScore"]),
		SupplySource:     StrVal(payload, "supplySource"),
		SourceTaskID:     StrVal(payload, "sourceTaskId"),
		AuditID:          StrVal(payload, "auditId"),
		RollbackToken:    StrVal(payload, "rollbackToken"),
		FeaturedAt:       parseEventTime(StrVal(payload, "featuredAt"), occurredAt),
		ExpiresAt:        parseEventTime(StrVal(payload, "expiresAt"), time.Time{}),
		TakedownEjected:  boolVal(payload, "takedownEjected"),
		UpdatedAt:        parseEventTime(StrVal(payload, "updatedAt"), occurredAt),
	}
}

func premiumPoolFloat(raw any) float64 {
	if v, ok := numericValue(raw); ok {
		return v
	}
	return 0
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

type mongoPremiumPoolProjectionWriter struct {
	coll *mongo.Collection
}

func (w mongoPremiumPoolProjectionWriter) UpsertPremiumProjection(ctx context.Context, fields bson.M) error {
	if w.coll == nil {
		return nil
	}
	contentID, _ := fields["contentId"].(string)
	contentID = strings.TrimSpace(contentID)
	if contentID == "" {
		return nil
	}
	_, err := w.coll.UpdateOne(
		ctx,
		bson.M{"contentId": contentID},
		bson.M{
			"$set": fields,
			"$setOnInsert": bson.M{
				"createdAt": time.Now().UTC(),
			},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func (w mongoPremiumPoolProjectionWriter) MarkPremiumProjectionTakedown(ctx context.Context, contentID string, now time.Time) error {
	if w.coll == nil {
		return nil
	}
	contentID = strings.TrimSpace(contentID)
	if contentID == "" {
		return nil
	}
	if now.IsZero() {
		now = time.Now().UTC()
	}
	_, err := w.coll.UpdateOne(
		ctx,
		bson.M{"contentId": contentID},
		bson.M{"$set": bson.M{
			"status":            "takedown_ejected",
			"eligibilityState":  "ineligible",
			"ineligibleReasons": []string{"takedown_ejected"},
			"takedownEjected":   true,
			"projectionVersion": PremiumPoolProjectionVersion,
			"updatedAt":         now.UTC(),
		}},
	)
	return err
}

// PremiumPoolEventConsumer subscribes product-ops events and forwards them to
// the read-model projector. It consumes events.ops.* only; feed reads never call
// product-ops synchronously.
type PremiumPoolEventConsumer struct {
	redis     rtredis.Client
	projector interface {
		Project(context.Context, ProjectorEvent) error
	}
	logger *slog.Logger
}

func NewPremiumPoolEventConsumer(redis rtredis.Client, projector interface {
	Project(context.Context, ProjectorEvent) error
}, logger *slog.Logger) *PremiumPoolEventConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	return &PremiumPoolEventConsumer{redis: redis, projector: projector, logger: logger}
}

func (c *PremiumPoolEventConsumer) Run(ctx context.Context) {
	if c == nil || c.redis == nil || c.projector == nil {
		return
	}
	sub, err := c.redis.Subscribe(ctx,
		PremiumPoolEntryUpsertedChannel,
		PremiumPoolEntryRolledBackChannel,
		PremiumPoolEntryTakedownEjectedChannel,
	)
	if err != nil {
		c.logger.Error("premium pool event consumer subscribe failed", "err", err)
		return
	}
	defer func() { _ = sub.Close() }()

	ch := sub.Channel()
	for {
		select {
		case <-ctx.Done():
			return
		case msg, ok := <-ch:
			if !ok {
				return
			}
			if err := c.ProcessMessage(ctx, msg.Channel, msg.Payload); err != nil {
				c.logger.Warn("premium pool event projection failed", "channel", msg.Channel, "err", err)
			}
		}
	}
}

func (c *PremiumPoolEventConsumer) ProcessMessage(ctx context.Context, _ string, raw string) error {
	if c == nil || c.projector == nil {
		return fmt.Errorf("premium pool consumer not configured")
	}
	event, err := decodePremiumPoolEventEnvelope(raw)
	if err != nil {
		return err
	}
	return c.projector.Project(ctx, event)
}

type premiumPoolEventEnvelope struct {
	Payload struct {
		Type          string         `json:"type"`
		AggregateType string         `json:"aggregateType"`
		AggregateID   string         `json:"aggregateId"`
		Data          map[string]any `json:"data"`
		OccurredAt    string         `json:"occurredAt"`
	} `json:"payload"`
}

func decodePremiumPoolEventEnvelope(raw string) (ProjectorEvent, error) {
	var envelope premiumPoolEventEnvelope
	if err := json.Unmarshal([]byte(raw), &envelope); err != nil {
		return ProjectorEvent{}, fmt.Errorf("decode premium pool envelope: %w", err)
	}
	payload := envelope.Payload.Data
	if payload == nil {
		payload = map[string]any{}
	}
	return ProjectorEvent{
		Type:          strings.TrimSpace(envelope.Payload.Type),
		AggregateType: strings.TrimSpace(envelope.Payload.AggregateType),
		AggregateID:   strings.TrimSpace(envelope.Payload.AggregateID),
		Payload:       payload,
		OccurredAt:    parseEventTime(envelope.Payload.OccurredAt, time.Time{}),
	}, nil
}

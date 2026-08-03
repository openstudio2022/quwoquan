package accesscontrol

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sort"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

const (
	PersonaRelationshipEventStream           = "events.user.persona_relationship"
	PersonaAccessProjectionDLQ               = "events.user.persona_access.dlq"
	PersonaAccessProjectionConsumerGroup     = "content-service-persona-access"
	ContentPersonaAccessProjectionCollection = "content_persona_access_projection"
	ContentPersonaAccessInboxCollection      = "content_persona_access_projection_inbox"
)

type PersonaRelationshipEventName string

const (
	PersonaFollowStateChanged PersonaRelationshipEventName = "PersonaFollowStateChanged"
	PersonaBlocked            PersonaRelationshipEventName = "PersonaBlocked"
	PersonaUnblocked          PersonaRelationshipEventName = "PersonaUnblocked"
)

// PersonaRelationshipEvent is the fully decoded durable event
// contract. Stream string values are parsed once at the transport boundary;
// projector code receives no dynamic maps.
type PersonaRelationshipEvent struct {
	EventID                 string
	EventName               PersonaRelationshipEventName
	PairID                  string
	SourcePersonaID         string
	TargetPersonaID         string
	Following               bool
	Version                 int64
	OccurredAt              time.Time
	ClearedFollowDirections int
}

type personaRelationshipProjectionWriter interface {
	ApplyBlocked(context.Context, PersonaRelationshipEvent) error
	ApplyUnblocked(context.Context, PersonaRelationshipEvent) error
	RecordAppliedEvent(context.Context, PersonaRelationshipEvent) (bool, error)
}

// PersonaAccessProjection owns Content's local authorization read model. It
// persists only block/unblock state and never copies follow relationships or
// reads the User domain's PostgreSQL store directly.
type PersonaAccessProjection struct {
	writer personaRelationshipProjectionWriter
}

func NewPersonaAccessProjection(db *mongo.Database) *PersonaAccessProjection {
	return NewPersonaAccessProjectionWithWriter(mongoPersonaRelationshipProjectionWriter{
		relationships: db.Collection(ContentPersonaAccessProjectionCollection),
		inbox:         db.Collection(ContentPersonaAccessInboxCollection),
	})
}

func NewPersonaAccessProjectionWithWriter(writer personaRelationshipProjectionWriter) *PersonaAccessProjection {
	return &PersonaAccessProjection{writer: writer}
}

func (p *PersonaAccessProjection) EnsureIndexes(ctx context.Context) error {
	writer, ok := p.writer.(mongoPersonaRelationshipProjectionWriter)
	if !ok {
		return nil
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "sourcePersonaId", Value: 1}, {Key: "targetPersonaId", Value: 1}},
		Options: options.Index().SetUnique(true).SetName("uq_content_persona_access_direction"),
	}); err != nil {
		return fmt.Errorf("create persona relationship projection direction index: %w", err)
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "sourcePersonaId", Value: 1},
			{Key: "blocked", Value: 1},
			{Key: "targetPersonaId", Value: 1},
		},
		Options: options.Index().SetName("idx_content_persona_access_source"),
	}); err != nil {
		return fmt.Errorf("create persona block projection source index: %w", err)
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "targetPersonaId", Value: 1},
			{Key: "blocked", Value: 1},
			{Key: "sourcePersonaId", Value: 1},
		},
		Options: options.Index().SetName("idx_content_persona_access_target"),
	}); err != nil {
		return fmt.Errorf("create persona block projection target index: %w", err)
	}
	if _, err := writer.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "eventId", Value: 1}},
		Options: options.Index().SetUnique(true).SetName("uq_content_persona_access_event"),
	}); err != nil {
		return fmt.Errorf("create persona relationship projection inbox index: %w", err)
	}
	return nil
}

// Apply uses event version guards for projection ordering. The inbox marker is
// written after the idempotent projection update: a crash before the marker is
// safe to replay, whereas a marker written first could lose a projection.
func (p *PersonaAccessProjection) Apply(ctx context.Context, event PersonaRelationshipEvent) error {
	if p == nil || p.writer == nil {
		return errors.New("persona relationship projection is not configured")
	}
	if err := validatePersonaRelationshipProjectionEvent(event); err != nil {
		return err
	}
	switch event.EventName {
	case PersonaFollowStateChanged:
		// Follow state belongs to RecommendationFeatureProfileView. Content
		// consumes the shared ordered stream but deliberately persists no copy.
	case PersonaBlocked:
		if err := p.writer.ApplyBlocked(ctx, event); err != nil {
			return err
		}
	case PersonaUnblocked:
		// Unblock intentionally does not restore a prior follow, but it must
		// clear the blocked marker so read-path enforcement stops rejecting.
		if err := p.writer.ApplyUnblocked(ctx, event); err != nil {
			return err
		}
	default:
		return fmt.Errorf("unsupported persona relationship event %q", event.EventName)
	}
	_, err := p.writer.RecordAppliedEvent(ctx, event)
	return err
}

func validatePersonaRelationshipProjectionEvent(event PersonaRelationshipEvent) error {
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.PairID) == "" ||
		strings.TrimSpace(event.SourcePersonaID) == "" || strings.TrimSpace(event.TargetPersonaID) == "" ||
		event.SourcePersonaID == event.TargetPersonaID || event.Version <= 0 || event.OccurredAt.IsZero() {
		return errors.New("invalid persona relationship projection event")
	}
	switch event.EventName {
	case PersonaFollowStateChanged, PersonaBlocked, PersonaUnblocked:
		return nil
	default:
		return fmt.Errorf("unsupported persona relationship event %q", event.EventName)
	}
}

type mongoPersonaRelationshipProjectionWriter struct {
	relationships *mongo.Collection
	inbox         *mongo.Collection
}

func (w mongoPersonaRelationshipProjectionWriter) ApplyBlocked(ctx context.Context, event PersonaRelationshipEvent) error {
	return w.applyBlockMarker(ctx, event, true)
}

func (w mongoPersonaRelationshipProjectionWriter) ApplyUnblocked(ctx context.Context, event PersonaRelationshipEvent) error {
	return w.applyBlockMarker(ctx, event, false)
}

// applyBlockMarker projects the directional "source blocked target" fact so
// read paths (author profile posts, feeds) can enforce block semantics
// server-side instead of trusting client-provided headers.
func (w mongoPersonaRelationshipProjectionWriter) applyBlockMarker(ctx context.Context, event PersonaRelationshipEvent, blocked bool) error {
	filter := blockMarkerVersionFilter(event.SourcePersonaID, event.TargetPersonaID, event.Version)
	_, err := w.relationships.UpdateOne(ctx, filter, bson.M{
		"$set": bson.M{
			"sourcePersonaId": event.SourcePersonaID,
			"targetPersonaId": event.TargetPersonaID,
			"blocked":         blocked,
			"pairId":          event.PairID,
			"blockVersion":    event.Version,
			"eventId":         event.EventID,
			"updatedAt":       event.OccurredAt.UTC(),
		},
	}, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		// A newer block/unblock event won a concurrent race; the version
		// predicate already protects newer state, so this is an idempotent no-op.
		return nil
	}
	if err != nil {
		return fmt.Errorf("project persona block marker: %w", err)
	}
	return nil
}

func blockMarkerVersionFilter(sourcePersonaID, targetPersonaID string, version int64) bson.M {
	return bson.M{
		"sourcePersonaId": sourcePersonaID,
		"targetPersonaId": targetPersonaID,
		"$or": []bson.M{
			{"blockVersion": bson.M{"$exists": false}},
			{"blockVersion": bson.M{"$lt": version}},
		},
	}
}

func (w mongoPersonaRelationshipProjectionWriter) RecordAppliedEvent(ctx context.Context, event PersonaRelationshipEvent) (bool, error) {
	_, err := w.inbox.InsertOne(ctx, bson.M{
		"eventId":         event.EventID,
		"eventName":       string(event.EventName),
		"pairId":          event.PairID,
		"sourcePersonaId": event.SourcePersonaID,
		"targetPersonaId": event.TargetPersonaID,
		"version":         event.Version,
		"appliedAt":       time.Now().UTC(),
	})
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("record persona relationship projection inbox: %w", err)
	}
	return true, nil
}

// PersonaBlockReader answers "does either side of viewer/author block the
// other" from the projected block markers. It implements the content domain's
// postports.ViewerBlockReader so author read paths enforce block semantics
// server-side without trusting client headers.
type PersonaBlockReader struct {
	relationships *mongo.Collection
}

func NewPersonaBlockReader(db *mongo.Database) *PersonaBlockReader {
	return &PersonaBlockReader{relationships: db.Collection(ContentPersonaAccessProjectionCollection)}
}

func (r *PersonaBlockReader) IsBlockedBetween(
	ctx context.Context,
	viewer postports.PersonaID,
	author postports.PersonaID,
) (bool, error) {
	viewerID := strings.TrimSpace(string(viewer))
	authorID := strings.TrimSpace(string(author))
	if r == nil || r.relationships == nil || viewerID == "" || authorID == "" || viewerID == authorID {
		return false, nil
	}
	count, err := r.relationships.CountDocuments(ctx, bson.M{
		"blocked": true,
		"$or": []bson.M{
			{"sourcePersonaId": viewerID, "targetPersonaId": authorID},
			{"sourcePersonaId": authorID, "targetPersonaId": viewerID},
		},
	}, options.Count().SetLimit(1))
	if err != nil {
		return false, fmt.Errorf("read persona block marker: %w", err)
	}
	return count > 0, nil
}

// ListBlockedPersonaIDs 返回与 viewer 任一方向存在显式拉黑标记的 persona。
// Feed 与 Comment 只消费该投影，不信任客户端自报的拉黑集合。
func (r *PersonaBlockReader) ListBlockedPersonaIDs(
	ctx context.Context,
	viewerPersonaID string,
) ([]string, error) {
	if r == nil || r.relationships == nil {
		return nil, fmt.Errorf("persona block projection is not configured")
	}
	viewerPersonaID = strings.TrimSpace(viewerPersonaID)
	if viewerPersonaID == "" {
		return []string{}, nil
	}
	cursor, err := r.relationships.Find(ctx, bson.M{
		"blocked": true,
		"$or": []bson.M{
			{
				"sourcePersonaId": viewerPersonaID,
				"targetPersonaId": bson.M{"$ne": viewerPersonaID},
			},
			{
				"sourcePersonaId": bson.M{"$ne": viewerPersonaID},
				"targetPersonaId": viewerPersonaID,
			},
		},
	})
	if err != nil {
		return nil, fmt.Errorf("list persona block markers: %w", err)
	}
	defer cursor.Close(ctx)

	blockedSet := map[string]struct{}{}
	for cursor.Next(ctx) {
		var relation struct {
			SourcePersonaID string `bson:"sourcePersonaId"`
			TargetPersonaID string `bson:"targetPersonaId"`
		}
		if err := cursor.Decode(&relation); err != nil {
			return nil, fmt.Errorf("decode persona block marker: %w", err)
		}
		otherPersonaID := strings.TrimSpace(relation.SourcePersonaID)
		if otherPersonaID == viewerPersonaID {
			otherPersonaID = strings.TrimSpace(relation.TargetPersonaID)
		}
		if otherPersonaID != "" && otherPersonaID != viewerPersonaID {
			blockedSet[otherPersonaID] = struct{}{}
		}
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate persona block markers: %w", err)
	}

	blocked := make([]string, 0, len(blockedSet))
	for personaID := range blockedSet {
		blocked = append(blocked, personaID)
	}
	sort.Strings(blocked)
	return blocked, nil
}

type personaRelationshipProjectionApplier interface {
	Apply(context.Context, PersonaRelationshipEvent) error
}

// PersonaAccessProjectionConsumer consumes the durable user-service
// stream through a consumer group. It acknowledges only after the projection
// and inbox record both succeed; malformed events are preserved in a DLQ.
type PersonaAccessProjectionConsumer struct {
	redis     rtredis.Client
	projector personaRelationshipProjectionApplier
	consumer  string
	logger    *slog.Logger
}

func NewPersonaAccessProjectionConsumer(redis rtredis.Client, projector personaRelationshipProjectionApplier, consumer string, logger *slog.Logger) *PersonaAccessProjectionConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-persona-relationship-worker"
	}
	return &PersonaAccessProjectionConsumer{redis: redis, projector: projector, consumer: consumer, logger: logger}
}

func (c *PersonaAccessProjectionConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return errors.New("persona relationship projection redis is not configured")
	}
	return c.redis.XGroupCreateMkStream(ctx, PersonaRelationshipEventStream, PersonaAccessProjectionConsumerGroup, "0")
}

func (c *PersonaAccessProjectionConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.projector == nil {
		return 0, errors.New("persona relationship projection consumer is not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := c.redis.XReadGroup(ctx, PersonaAccessProjectionConsumerGroup, c.consumer,
		map[string]string{PersonaRelationshipEventStream: ">"}, 20, 200*time.Millisecond)
	if err != nil {
		return 0, err
	}
	processed := 0
	for _, message := range messages {
		if err := c.processMessage(ctx, message); err != nil {
			if dlqErr := c.deadLetter(ctx, message, err); dlqErr != nil {
				return processed, dlqErr
			}
			c.logger.ErrorContext(ctx, "persona relationship projection sent to dead letter queue",
				slog.String("streamId", message.ID), slog.String("err", err.Error()))
		}
		if err := c.redis.XAck(ctx, PersonaRelationshipEventStream, PersonaAccessProjectionConsumerGroup, message.ID); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (c *PersonaAccessProjectionConsumer) Run(ctx context.Context, interval time.Duration) {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.logger.ErrorContext(ctx, "persona relationship projection consumer ensure group failed", slog.String("err", err.Error()))
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil {
			c.logger.ErrorContext(ctx, "persona relationship projection consume failed", slog.String("err", err.Error()))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *PersonaAccessProjectionConsumer) processMessage(ctx context.Context, message rtredis.StreamMessage) error {
	event, err := decodePersonaRelationshipProjectionEvent(message.Values)
	if err != nil {
		return err
	}
	return c.projector.Apply(ctx, event)
}

func (c *PersonaAccessProjectionConsumer) deadLetter(ctx context.Context, message rtredis.StreamMessage, cause error) error {
	values := map[string]string{
		"streamId": message.ID,
		"error":    cause.Error(),
	}
	for key, value := range message.Values {
		values[key] = value
	}
	if _, err := c.redis.XAdd(ctx, PersonaAccessProjectionDLQ, values); err != nil {
		return fmt.Errorf("append persona relationship projection dlq: %w", err)
	}
	return nil
}

func decodePersonaRelationshipProjectionEvent(values map[string]string) (PersonaRelationshipEvent, error) {
	version, err := strconv.ParseInt(strings.TrimSpace(values["version"]), 10, 64)
	if err != nil || version <= 0 {
		return PersonaRelationshipEvent{}, errors.New("invalid persona relationship event version")
	}
	following, err := strconv.ParseBool(strings.TrimSpace(values["following"]))
	if err != nil {
		return PersonaRelationshipEvent{}, errors.New("invalid persona relationship following value")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return PersonaRelationshipEvent{}, errors.New("invalid persona relationship occurredAt")
	}
	cleared := 0
	if raw := strings.TrimSpace(values["clearedFollowDirections"]); raw != "" {
		cleared, err = strconv.Atoi(raw)
		if err != nil || cleared < 0 {
			return PersonaRelationshipEvent{}, errors.New("invalid persona relationship clearedFollowDirections")
		}
	}
	event := PersonaRelationshipEvent{
		EventID: strings.TrimSpace(values["eventId"]), EventName: PersonaRelationshipEventName(strings.TrimSpace(values["eventName"])),
		PairID: strings.TrimSpace(values["pairId"]), SourcePersonaID: strings.TrimSpace(values["sourcePersonaId"]),
		TargetPersonaID: strings.TrimSpace(values["targetPersonaId"]), Following: following, Version: version,
		OccurredAt: occurredAt.UTC(), ClearedFollowDirections: cleared,
	}
	return event, validatePersonaRelationshipProjectionEvent(event)
}

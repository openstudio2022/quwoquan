package recommendation

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
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

const (
	PersonaRelationshipEventStream             = "events.user.persona_relationship"
	PersonaRelationshipProjectionDLQ           = "events.user.persona_relationship.dlq"
	personaRelationshipProjectionConsumerGroup = "content-service-persona-relationship"
)

type PersonaRelationshipEventName string

const (
	PersonaFollowStateChanged PersonaRelationshipEventName = "PersonaFollowStateChanged"
	PersonaBlocked            PersonaRelationshipEventName = "PersonaBlocked"
	PersonaUnblocked          PersonaRelationshipEventName = "PersonaUnblocked"
)

// PersonaRelationshipProjectionEvent is the fully decoded durable event
// contract. Stream string values are parsed once at the transport boundary;
// projector code receives no dynamic maps.
type PersonaRelationshipProjectionEvent struct {
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
	ApplyFollowState(context.Context, PersonaRelationshipProjectionEvent) error
	ApplyBlocked(context.Context, PersonaRelationshipProjectionEvent) error
	ApplyUnblocked(context.Context, PersonaRelationshipProjectionEvent) error
	RecordAppliedEvent(context.Context, PersonaRelationshipProjectionEvent) (bool, error)
}

// PersonaRelationshipProjection owns only the content-service read model. It
// never reads the user domain's PostgreSQL store directly.
type PersonaRelationshipProjection struct {
	writer personaRelationshipProjectionWriter
}

func NewPersonaRelationshipProjection(db *mongo.Database) *PersonaRelationshipProjection {
	return newPersonaRelationshipProjection(mongoPersonaRelationshipProjectionWriter{
		relationships: db.Collection("persona_follow_projection"),
		inbox:         db.Collection("persona_relationship_projection_inbox"),
	})
}

func newPersonaRelationshipProjection(writer personaRelationshipProjectionWriter) *PersonaRelationshipProjection {
	return &PersonaRelationshipProjection{writer: writer}
}

func (p *PersonaRelationshipProjection) EnsureIndexes(ctx context.Context) error {
	writer, ok := p.writer.(mongoPersonaRelationshipProjectionWriter)
	if !ok {
		return nil
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "sourcePersonaId", Value: 1}, {Key: "targetPersonaId", Value: 1}},
		Options: options.Index().SetUnique(true).SetName("uq_persona_follow_projection_direction"),
	}); err != nil {
		return fmt.Errorf("create persona relationship projection direction index: %w", err)
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "sourcePersonaId", Value: 1},
			{Key: "blocked", Value: 1},
			{Key: "targetPersonaId", Value: 1},
		},
		Options: options.Index().SetName("idx_persona_block_projection_source"),
	}); err != nil {
		return fmt.Errorf("create persona block projection source index: %w", err)
	}
	if _, err := writer.relationships.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "targetPersonaId", Value: 1},
			{Key: "blocked", Value: 1},
			{Key: "sourcePersonaId", Value: 1},
		},
		Options: options.Index().SetName("idx_persona_block_projection_target"),
	}); err != nil {
		return fmt.Errorf("create persona block projection target index: %w", err)
	}
	if _, err := writer.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "eventId", Value: 1}},
		Options: options.Index().SetUnique(true).SetName("uq_persona_relationship_projection_event"),
	}); err != nil {
		return fmt.Errorf("create persona relationship projection inbox index: %w", err)
	}
	return nil
}

// Apply uses event version guards for projection ordering. The inbox marker is
// written after the idempotent projection update: a crash before the marker is
// safe to replay, whereas a marker written first could lose a projection.
func (p *PersonaRelationshipProjection) Apply(ctx context.Context, event PersonaRelationshipProjectionEvent) error {
	if p == nil || p.writer == nil {
		return errors.New("persona relationship projection is not configured")
	}
	if err := validatePersonaRelationshipProjectionEvent(event); err != nil {
		return err
	}
	switch event.EventName {
	case PersonaFollowStateChanged:
		if err := p.writer.ApplyFollowState(ctx, event); err != nil {
			return err
		}
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

func validatePersonaRelationshipProjectionEvent(event PersonaRelationshipProjectionEvent) error {
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

func (w mongoPersonaRelationshipProjectionWriter) ApplyFollowState(ctx context.Context, event PersonaRelationshipProjectionEvent) error {
	filter := directionalProjectionVersionFilter(event.SourcePersonaID, event.TargetPersonaID, event.Version)
	_, err := w.relationships.UpdateOne(ctx, filter, bson.M{
		"$set": bson.M{
			"sourcePersonaId": event.SourcePersonaID,
			"targetPersonaId": event.TargetPersonaID,
			"following":       event.Following,
			"pairId":          event.PairID,
			"version":         event.Version,
			"eventId":         event.EventID,
			"updatedAt":       event.OccurredAt.UTC(),
		},
	}, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		// A newer version won a concurrent race. The version predicate prevents
		// stale state from overwriting it, so treating this as an idempotent no-op
		// is correct.
		return nil
	}
	if err != nil {
		return fmt.Errorf("project persona follow state: %w", err)
	}
	return nil
}

func (w mongoPersonaRelationshipProjectionWriter) ApplyBlocked(ctx context.Context, event PersonaRelationshipProjectionEvent) error {
	if err := w.ApplyFollowState(ctx, PersonaRelationshipProjectionEvent{
		EventID: event.EventID, EventName: PersonaFollowStateChanged, PairID: event.PairID,
		SourcePersonaID: event.SourcePersonaID, TargetPersonaID: event.TargetPersonaID,
		Following: false, Version: event.Version, OccurredAt: event.OccurredAt,
	}); err != nil {
		return err
	}
	filter := bson.M{
		"sourcePersonaId": event.TargetPersonaID,
		"targetPersonaId": event.SourcePersonaID,
		"$or": []bson.M{
			{"version": bson.M{"$exists": false}},
			{"version": bson.M{"$lt": event.Version}},
		},
	}
	_, err := w.relationships.UpdateOne(ctx, filter, bson.M{
		"$set": bson.M{
			"following": false,
			"pairId":    event.PairID,
			"version":   event.Version,
			"eventId":   event.EventID,
			"updatedAt": event.OccurredAt.UTC(),
		},
	})
	if err != nil {
		return fmt.Errorf("clear reciprocal persona follow state: %w", err)
	}
	return w.applyBlockMarker(ctx, event, true)
}

func (w mongoPersonaRelationshipProjectionWriter) ApplyUnblocked(ctx context.Context, event PersonaRelationshipProjectionEvent) error {
	return w.applyBlockMarker(ctx, event, false)
}

// applyBlockMarker projects the directional "source blocked target" fact so
// read paths (author profile posts, feeds) can enforce block semantics
// server-side instead of trusting client-provided headers.
func (w mongoPersonaRelationshipProjectionWriter) applyBlockMarker(ctx context.Context, event PersonaRelationshipProjectionEvent, blocked bool) error {
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

func directionalProjectionVersionFilter(sourcePersonaID, targetPersonaID string, version int64) bson.M {
	return bson.M{
		"sourcePersonaId": sourcePersonaID,
		"targetPersonaId": targetPersonaID,
		"$or": []bson.M{
			{"version": bson.M{"$exists": false}},
			{"version": bson.M{"$lt": version}},
		},
	}
}

func (w mongoPersonaRelationshipProjectionWriter) RecordAppliedEvent(ctx context.Context, event PersonaRelationshipProjectionEvent) (bool, error) {
	_, err := w.inbox.InsertOne(ctx, bson.M{
		"eventId":   event.EventID,
		"eventName": string(event.EventName),
		"pairId":    event.PairID,
		"version":   event.Version,
		"appliedAt": time.Now().UTC(),
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
	return &PersonaBlockReader{relationships: db.Collection("persona_follow_projection")}
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
	Apply(context.Context, PersonaRelationshipProjectionEvent) error
}

// PersonaRelationshipProjectionConsumer consumes the durable user-service
// stream through a consumer group. It acknowledges only after the projection
// and inbox record both succeed; malformed events are preserved in a DLQ.
type PersonaRelationshipProjectionConsumer struct {
	redis     rtredis.Client
	projector personaRelationshipProjectionApplier
	consumer  string
	logger    *slog.Logger
}

func NewPersonaRelationshipProjectionConsumer(redis rtredis.Client, projector personaRelationshipProjectionApplier, consumer string, logger *slog.Logger) *PersonaRelationshipProjectionConsumer {
	if logger == nil {
		logger = slog.Default()
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		consumer = "content-persona-relationship-worker"
	}
	return &PersonaRelationshipProjectionConsumer{redis: redis, projector: projector, consumer: consumer, logger: logger}
}

func (c *PersonaRelationshipProjectionConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.redis == nil {
		return errors.New("persona relationship projection redis is not configured")
	}
	return c.redis.XGroupCreateMkStream(ctx, PersonaRelationshipEventStream, personaRelationshipProjectionConsumerGroup, "0")
}

func (c *PersonaRelationshipProjectionConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.redis == nil || c.projector == nil {
		return 0, errors.New("persona relationship projection consumer is not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		return 0, err
	}
	messages, err := c.redis.XReadGroup(ctx, personaRelationshipProjectionConsumerGroup, c.consumer,
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
		if err := c.redis.XAck(ctx, PersonaRelationshipEventStream, personaRelationshipProjectionConsumerGroup, message.ID); err != nil {
			return processed, err
		}
		processed++
	}
	return processed, nil
}

func (c *PersonaRelationshipProjectionConsumer) Run(ctx context.Context, interval time.Duration) {
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

func (c *PersonaRelationshipProjectionConsumer) processMessage(ctx context.Context, message rtredis.StreamMessage) error {
	event, err := decodePersonaRelationshipProjectionEvent(message.Values)
	if err != nil {
		return err
	}
	return c.projector.Apply(ctx, event)
}

func (c *PersonaRelationshipProjectionConsumer) deadLetter(ctx context.Context, message rtredis.StreamMessage, cause error) error {
	values := map[string]string{
		"streamId": message.ID,
		"error":    cause.Error(),
	}
	for key, value := range message.Values {
		values[key] = value
	}
	if _, err := c.redis.XAdd(ctx, PersonaRelationshipProjectionDLQ, values); err != nil {
		return fmt.Errorf("append persona relationship projection dlq: %w", err)
	}
	return nil
}

func decodePersonaRelationshipProjectionEvent(values map[string]string) (PersonaRelationshipProjectionEvent, error) {
	version, err := strconv.ParseInt(strings.TrimSpace(values["version"]), 10, 64)
	if err != nil || version <= 0 {
		return PersonaRelationshipProjectionEvent{}, errors.New("invalid persona relationship event version")
	}
	following, err := strconv.ParseBool(strings.TrimSpace(values["following"]))
	if err != nil {
		return PersonaRelationshipProjectionEvent{}, errors.New("invalid persona relationship following value")
	}
	occurredAt, err := time.Parse(time.RFC3339Nano, strings.TrimSpace(values["occurredAt"]))
	if err != nil {
		return PersonaRelationshipProjectionEvent{}, errors.New("invalid persona relationship occurredAt")
	}
	cleared := 0
	if raw := strings.TrimSpace(values["clearedFollowDirections"]); raw != "" {
		cleared, err = strconv.Atoi(raw)
		if err != nil || cleared < 0 {
			return PersonaRelationshipProjectionEvent{}, errors.New("invalid persona relationship clearedFollowDirections")
		}
	}
	event := PersonaRelationshipProjectionEvent{
		EventID: strings.TrimSpace(values["eventId"]), EventName: PersonaRelationshipEventName(strings.TrimSpace(values["eventName"])),
		PairID: strings.TrimSpace(values["pairId"]), SourcePersonaID: strings.TrimSpace(values["sourcePersonaId"]),
		TargetPersonaID: strings.TrimSpace(values["targetPersonaId"]), Following: following, Version: version,
		OccurredAt: occurredAt.UTC(), ClearedFollowDirections: cleared,
	}
	return event, validatePersonaRelationshipProjectionEvent(event)
}

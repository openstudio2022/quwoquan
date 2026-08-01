package recommendation

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemessaging "quwoquan_service/runtime/messaging"
)

const (
	TagFeedbackStream        = "events.tag.feedback"
	TagFeedbackConsumerGroup = "content-service-tag-feedback"
	TagFeedbackDLQ           = "events.tag.feedback.content-service.dlq"

	tagFeedbackInboxCollection = "rm_tag_feedback_fact_inbox"
	tagFeedbackBatchSize       = int64(20)
	tagFeedbackMinIdle         = 30 * time.Second
	tagFeedbackPollInterval    = 500 * time.Millisecond
	tagFeedbackDLQRetention    = 7 * 24 * time.Hour
)

// TagFeedbackFeatureProjector persists the consumer receipt and the
// recommendation feature update in one Mongo transaction. A Redis consumer
// group can redeliver at any time; the receipt is the permanent idempotency
// boundary, so a successfully committed event is always safe to ACK.
type TagFeedbackFeatureProjector struct {
	db        *mongo.Database
	inbox     *mongo.Collection
	features  *mongo.Collection
	onApplied func(actorID string)
}

func NewTagFeedbackFeatureProjector(
	db *mongo.Database,
	onApplied func(actorID string),
) (*TagFeedbackFeatureProjector, error) {
	if db == nil {
		return nil, errors.New("tag feedback feature projector requires database")
	}
	return &TagFeedbackFeatureProjector{
		db:        db,
		inbox:     db.Collection(tagFeedbackInboxCollection),
		features:  db.Collection("rm_recommend_feature"),
		onApplied: onApplied,
	}, nil
}

func (p *TagFeedbackFeatureProjector) EnsureIndexes(ctx context.Context) error {
	if p == nil || p.inbox == nil {
		return errors.New("tag feedback feature projector is not configured")
	}
	_, err := p.inbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "recordedAt", Value: -1}},
		Options: options.Index().SetName("idx_rm_tag_feedback_fact_inbox_recorded_at"),
	})
	if err != nil {
		return fmt.Errorf("create tag feedback inbox index: %w", err)
	}
	return nil
}

// Apply returns replayed=true only when the same immutable event already
// committed. Invalid envelopes are rejected before a transaction and must be
// quarantined by the transport consumer.
func (p *TagFeedbackFeatureProjector) Apply(
	ctx context.Context,
	event TagFeedbackRecorded,
) (replayed bool, err error) {
	if p == nil || p.db == nil || p.inbox == nil || p.features == nil {
		return false, errors.New("tag feedback feature projector is not configured")
	}
	if err := event.Validate(); err != nil {
		return false, err
	}

	session, err := p.db.Client().StartSession()
	if err != nil {
		return false, fmt.Errorf("start tag feedback feature transaction: %w", err)
	}
	defer session.EndSession(ctx)

	replayed = false
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var existing tagFeedbackInboxReceipt
		receiptErr := p.inbox.FindOne(
			txCtx,
			bson.M{"_id": event.EventID},
		).Decode(&existing)
		switch {
		case receiptErr == nil:
			if !existing.matches(event) {
				return nil, malformedTagFeedback("conflicting_event_id")
			}
			replayed = true
			return nil, nil
		case !errors.Is(receiptErr, mongo.ErrNoDocuments):
			return nil, fmt.Errorf("read tag feedback inbox receipt: %w", receiptErr)
		}
		_, insertErr := p.inbox.InsertOne(txCtx, bson.M{
			"_id":        event.EventID,
			"actorId":    event.ActorID,
			"actorKind":  event.ActorKind,
			"tagRef":     event.TagRef,
			"action":     event.Action,
			"recordedAt": event.RecordedAt,
			"appliedAt":  time.Now().UTC(),
		})
		if insertErr != nil {
			return nil, fmt.Errorf("persist tag feedback inbox receipt: %w", insertErr)
		}
		if applyErr := p.applyFeature(txCtx, event); applyErr != nil {
			return nil, applyErr
		}
		return nil, nil
	})
	if err != nil {
		return false, err
	}
	if !replayed && p.onApplied != nil {
		p.onApplied(event.ActorID)
	}
	return replayed, nil
}

type tagFeedbackInboxReceipt struct {
	EventID    string    `bson:"_id"`
	ActorID    string    `bson:"actorId"`
	ActorKind  string    `bson:"actorKind"`
	TagRef     string    `bson:"tagRef"`
	Action     string    `bson:"action"`
	RecordedAt time.Time `bson:"recordedAt"`
}

func (receipt tagFeedbackInboxReceipt) matches(event TagFeedbackRecorded) bool {
	return receipt.EventID == event.EventID &&
		receipt.ActorID == event.ActorID &&
		receipt.ActorKind == event.ActorKind &&
		receipt.TagRef == event.TagRef &&
		receipt.Action == event.Action &&
		receipt.RecordedAt.Equal(event.RecordedAt)
}

// TagFeedbackFeatureDelta 描述一条反馈对 explicitTagAffinities 的作用。
type TagFeedbackFeatureDelta struct {
	// Unchanged 表示反馈只落成收据，不改变特征。
	Unchanged bool
	// Clears 表示删除既有偏好，回到「无偏好」，而不是写入负偏好。
	Clears bool
	// Weight 是 Unchanged 与 Clears 均为 false 时写入的权重。
	Weight float64
}

// ResolveTagFeedbackFeatureDelta 把 TagFeedbackAction 翻译成特征写入语义。
// 取值集合与 tag-service 的 TagFeedbackAction 契约同源，未登记取值必须报错而
// 不能退化成中性处理，否则负向信号会被静默吞掉。
func ResolveTagFeedbackFeatureDelta(action string) (TagFeedbackFeatureDelta, error) {
	switch action {
	case "click":
		return TagFeedbackFeatureDelta{Weight: 1.0}, nil
	case "dislike":
		// 排序侧对 tagAffinities 做加法，所以负权重直接压低带该标签的候选。
		// 与 ignore 的区别是 ignore 只回到「无偏好」，dislike 会持续扣分。
		return TagFeedbackFeatureDelta{Weight: -1.0}, nil
	case "ignore":
		return TagFeedbackFeatureDelta{Clears: true}, nil
	case "correct":
		// `correct` identifies a bad recommendation but carries no replacement
		// tag. Treating it as either positive or negative preference would invent
		// user intent, so the durable receipt records it without changing features.
		return TagFeedbackFeatureDelta{Unchanged: true}, nil
	default:
		return TagFeedbackFeatureDelta{}, malformedTagFeedback("unsupported_action")
	}
}

func (p *TagFeedbackFeatureProjector) applyFeature(
	ctx context.Context,
	event TagFeedbackRecorded,
) error {
	delta, err := ResolveTagFeedbackFeatureDelta(event.Action)
	if err != nil {
		return err
	}
	if delta.Unchanged {
		return nil
	}

	field := "userFeatures.explicitTagAffinities." + event.TagRef
	update := bson.M{
		"$set": bson.M{
			"userId":    event.ActorID,
			"updatedAt": event.RecordedAt,
		},
	}
	if delta.Clears {
		update["$unset"] = bson.M{field: ""}
	} else {
		update["$set"].(bson.M)[field] = delta.Weight
	}
	if _, err := p.features.UpdateOne(
		ctx,
		bson.M{"userId": event.ActorID},
		update,
		options.UpdateOne().SetUpsert(true),
	); err != nil {
		return fmt.Errorf("project explicit tag preference: %w", err)
	}
	return nil
}

// TagFeedbackConsumer consumes the metadata-owned TagFeedbackRecorded stream.
// It reclaims the Redis PEL before reading fresh deliveries; only a committed
// Mongo inbox receipt (or a sanitized terminal DLQ record) is acknowledged.
type TagFeedbackConsumer struct {
	transport runtimemessaging.DurableDeliveryTransport
	projector *TagFeedbackFeatureProjector
	consumer  string
	logger    *slog.Logger

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure string
}

func NewTagFeedbackConsumer(
	transport runtimemessaging.DurableDeliveryTransport,
	projector *TagFeedbackFeatureProjector,
	consumer string,
	logger *slog.Logger,
) (*TagFeedbackConsumer, error) {
	if transport == nil || projector == nil {
		return nil, errors.New("tag feedback consumer requires transport and projector")
	}
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return nil, errors.New("tag feedback consumer name is required")
	}
	if logger == nil {
		logger = slog.Default()
	}
	return &TagFeedbackConsumer{
		transport: transport,
		projector: projector,
		consumer:  consumer,
		logger:    logger,
	}, nil
}

func (c *TagFeedbackConsumer) EnsureGroup(ctx context.Context) error {
	if c == nil || c.transport == nil {
		return errors.New("tag feedback consumer is not configured")
	}
	if err := c.transport.EnsureDurableConsumerGroup(
		ctx,
		TagFeedbackStream,
		TagFeedbackConsumerGroup,
		"0",
	); err != nil {
		return fmt.Errorf("ensure TagFeedbackRecorded consumer group: %w", err)
	}
	if err := c.transport.SetDurableRetention(
		ctx,
		TagFeedbackDLQ,
		tagFeedbackDLQRetention,
	); err != nil {
		return fmt.Errorf("set tag feedback DLQ retention: %w", err)
	}
	return nil
}

func (c *TagFeedbackConsumer) ProcessOnce(ctx context.Context) (int, error) {
	if c == nil || c.transport == nil || c.projector == nil {
		return 0, errors.New("tag feedback consumer is not configured")
	}
	if err := c.EnsureGroup(ctx); err != nil {
		c.recordFailure(err)
		return 0, err
	}
	reclaimed, _, err := c.transport.ReclaimDurable(
		ctx,
		TagFeedbackStream,
		TagFeedbackConsumerGroup,
		c.consumer,
		tagFeedbackMinIdle,
		"0-0",
		tagFeedbackBatchSize,
	)
	if err != nil {
		err = fmt.Errorf("reclaim TagFeedbackRecorded deliveries: %w", err)
		c.recordFailure(err)
		return 0, err
	}
	fresh, err := c.transport.ReadDurable(ctx, runtimemessaging.StreamReadRequest{
		Stream:   TagFeedbackStream,
		Group:    TagFeedbackConsumerGroup,
		Consumer: c.consumer,
		Count:    tagFeedbackBatchSize,
		Block:    200 * time.Millisecond,
	})
	if err != nil {
		err = fmt.Errorf("read TagFeedbackRecorded deliveries: %w", err)
		c.recordFailure(err)
		return 0, err
	}

	processed := 0
	for _, delivery := range uniqueTagFeedbackDeliveries(reclaimed, fresh) {
		if err := c.processDelivery(ctx, delivery); err != nil {
			c.recordFailure(err)
			return processed, err
		}
		processed++
	}
	c.recordSuccess()
	return processed, nil
}

func (c *TagFeedbackConsumer) processDelivery(
	ctx context.Context,
	delivery runtimemessaging.StreamDelivery,
) error {
	event, err := DecodeTagFeedbackRecorded(delivery)
	if err != nil {
		if !isMalformedTagFeedback(err) {
			return err
		}
		if _, dlqErr := c.transport.PublishDeadLetter(ctx, runtimemessaging.DeadLetterMessage{
			SourceStream:      TagFeedbackStream,
			DestinationStream: TagFeedbackDLQ,
			SourceID:          delivery.ID,
			Reason:            err.Error(),
			Fields: []runtimemessaging.DurableField{
				{Name: "eventIdDigest", Value: tagFeedbackDigest(fieldValue(delivery.Fields, "eventId"))},
				{Name: "payloadDigest", Value: tagFeedbackPayloadDigest(delivery.Fields)},
			},
		}); dlqErr != nil {
			return fmt.Errorf("dead-letter malformed TagFeedbackRecorded delivery: %w", dlqErr)
		}
		if ackErr := c.transport.AckDurable(
			ctx,
			TagFeedbackStream,
			TagFeedbackConsumerGroup,
			delivery.ID,
		); ackErr != nil {
			return fmt.Errorf("ack malformed TagFeedbackRecorded delivery: %w", ackErr)
		}
		c.logger.WarnContext(
			ctx,
			"malformed TagFeedbackRecorded delivery quarantined",
			slog.String("streamId", delivery.ID),
			slog.String("reason", err.Error()),
		)
		tagFeedbackConsumerTotal.WithLabelValues("dlq").Inc()
		return nil
	}
	replayed, err := c.projector.Apply(ctx, event)
	if err != nil {
		return fmt.Errorf("apply TagFeedbackRecorded feature projection: %w", err)
	}
	if err := c.transport.AckDurable(
		ctx,
		TagFeedbackStream,
		TagFeedbackConsumerGroup,
		delivery.ID,
	); err != nil {
		return fmt.Errorf("ack TagFeedbackRecorded delivery: %w", err)
	}
	outcome := "applied"
	if replayed {
		outcome = "replayed"
	}
	tagFeedbackConsumerTotal.WithLabelValues(outcome).Inc()
	lag := time.Since(event.RecordedAt)
	if lag < 0 {
		lag = 0
	}
	tagFeedbackConsumerLagSeconds.Observe(lag.Seconds())
	c.logger.DebugContext(
		ctx,
		"TagFeedbackRecorded delivery processed",
		slog.String("streamId", delivery.ID),
		slog.String("outcome", outcome),
	)
	return nil
}

func (c *TagFeedbackConsumer) Run(ctx context.Context) {
	ticker := time.NewTicker(tagFeedbackPollInterval)
	defer ticker.Stop()
	for {
		if _, err := c.ProcessOnce(ctx); err != nil && ctx.Err() == nil {
			c.logger.ErrorContext(
				ctx,
				"TagFeedbackRecorded consumer scan failed",
				slog.String("error", err.Error()),
			)
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (c *TagFeedbackConsumer) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 30 * time.Second
	}
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.lastSuccess.IsZero() {
		return errors.New("TagFeedbackRecorded consumer has not completed a scan")
	}
	if c.lastFailure != "" {
		return fmt.Errorf("TagFeedbackRecorded consumer last scan failed (digest=%s)", c.lastFailure)
	}
	if time.Since(c.lastSuccess) > maxStaleness {
		return errors.New("TagFeedbackRecorded consumer heartbeat is stale")
	}
	return nil
}

func (c *TagFeedbackConsumer) recordSuccess() {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastSuccess = time.Now().UTC()
	c.lastFailure = ""
	tagFeedbackConsumerLastSuccessUnix.Set(float64(c.lastSuccess.Unix()))
}

func (c *TagFeedbackConsumer) recordFailure(err error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.lastFailure = tagFeedbackDigest(err.Error())
	tagFeedbackConsumerTotal.WithLabelValues("failed").Inc()
}

type TagFeedbackRecorded struct {
	EventID    string
	ActorID    string
	ActorKind  string
	TagRef     string
	Action     string
	RecordedAt time.Time
}

func DecodeTagFeedbackRecorded(
	delivery runtimemessaging.StreamDelivery,
) (TagFeedbackRecorded, error) {
	if strings.TrimSpace(delivery.Stream) != TagFeedbackStream ||
		strings.TrimSpace(delivery.ID) == "" {
		return TagFeedbackRecorded{}, malformedTagFeedback("invalid_delivery_coordinate")
	}
	expected := map[string]struct{}{
		"eventName": {}, "eventId": {}, "id": {}, "actorId": {},
		"actorKind": {}, "tagRef": {}, "action": {}, "recordedAt": {},
	}
	values := make(map[string]string, len(delivery.Fields))
	for _, field := range delivery.Fields {
		name := strings.TrimSpace(field.Name)
		if _, ok := expected[name]; !ok {
			return TagFeedbackRecorded{}, malformedTagFeedback("unexpected_envelope_field")
		}
		if _, duplicate := values[name]; duplicate {
			return TagFeedbackRecorded{}, malformedTagFeedback("duplicate_envelope_field")
		}
		values[name] = strings.TrimSpace(field.Value)
	}
	if len(values) != len(expected) || values["eventName"] != "TagFeedbackRecorded" {
		return TagFeedbackRecorded{}, malformedTagFeedback("invalid_envelope_shape")
	}
	event := TagFeedbackRecorded{
		EventID:   values["eventId"],
		ActorID:   values["actorId"],
		ActorKind: values["actorKind"],
		TagRef:    values["tagRef"],
		Action:    strings.ToLower(values["action"]),
	}
	if event.EventID == "" || values["id"] != event.EventID ||
		event.ActorID == "" || event.ActorKind == "" || event.TagRef == "" {
		return TagFeedbackRecorded{}, malformedTagFeedback("incomplete_envelope")
	}
	recordedAt, err := time.Parse(time.RFC3339Nano, values["recordedAt"])
	if err != nil {
		return TagFeedbackRecorded{}, malformedTagFeedback("invalid_recorded_at")
	}
	event.RecordedAt = recordedAt.UTC()
	if err := event.Validate(); err != nil {
		return TagFeedbackRecorded{}, err
	}
	return event, nil
}

func (event TagFeedbackRecorded) Validate() error {
	if strings.TrimSpace(event.EventID) == "" ||
		strings.TrimSpace(event.ActorID) == "" ||
		(event.ActorKind != "persona" && event.ActorKind != "device") ||
		!safeTagFeedbackMapKey(event.TagRef) ||
		event.RecordedAt.IsZero() {
		return malformedTagFeedback("invalid_event")
	}
	switch event.Action {
	case "click", "ignore", "correct", "dislike":
		return nil
	default:
		return malformedTagFeedback("unsupported_action")
	}
}

func safeTagFeedbackMapKey(tagRef string) bool {
	tagRef = strings.TrimSpace(tagRef)
	return tagRef != "" &&
		!strings.ContainsAny(tagRef, ".\x00") &&
		!strings.HasPrefix(tagRef, "$")
}

type malformedTagFeedbackError struct {
	code string
}

func (err malformedTagFeedbackError) Error() string { return err.code }

func malformedTagFeedback(code string) error {
	return malformedTagFeedbackError{code: code}
}

func isMalformedTagFeedback(err error) bool {
	var malformed malformedTagFeedbackError
	return errors.As(err, &malformed)
}

func uniqueTagFeedbackDeliveries(
	groups ...[]runtimemessaging.StreamDelivery,
) []runtimemessaging.StreamDelivery {
	seen := map[string]struct{}{}
	out := make([]runtimemessaging.StreamDelivery, 0)
	for _, group := range groups {
		for _, delivery := range group {
			if _, exists := seen[delivery.ID]; exists {
				continue
			}
			seen[delivery.ID] = struct{}{}
			out = append(out, delivery)
		}
	}
	return out
}

func fieldValue(fields []runtimemessaging.DurableField, name string) string {
	for _, field := range fields {
		if field.Name == name {
			return field.Value
		}
	}
	return ""
}

func tagFeedbackDigest(value string) string {
	digest := sha256.Sum256([]byte(value))
	return fmt.Sprintf("%x", digest)
}

func tagFeedbackPayloadDigest(fields []runtimemessaging.DurableField) string {
	parts := make([]string, 0, len(fields))
	for _, field := range fields {
		parts = append(parts, field.Name+"="+field.Value)
	}
	return tagFeedbackDigest(strings.Join(parts, "\x00"))
}

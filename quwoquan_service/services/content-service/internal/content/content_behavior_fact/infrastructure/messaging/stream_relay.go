package messaging

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	redisruntime "quwoquan_service/runtime/redis"
)

const (
	BehaviorFactStream           = "events.content.behavior_facts"
	behaviorCheckpointCollection = "content_behavior_stream_checkpoints"
	behaviorStreamConsumer       = "recommendation-behavior-facts"
	behaviorStreamRetention      = 7 * 24 * time.Hour
	defaultWatermarkLag          = 2 * time.Second
	defaultLeaseTTL              = 15 * time.Second
)

type BehaviorFactDocument struct {
	ID                     bson.ObjectID `bson:"_id"`
	ClientEventID          string        `bson:"clientEventId"`
	UserID                 string        `bson:"userId"`
	DeviceActorID          string        `bson:"deviceActorId"`
	SessionID              string        `bson:"sessionId"`
	ContentID              string        `bson:"contentId"`
	Action                 string        `bson:"action"`
	State                  string        `bson:"state"`
	ContentType            string        `bson:"contentType"`
	Duration               float64       `bson:"duration"`
	FeedRequestID          string        `bson:"feedRequestId"`
	Tags                   []string      `bson:"tagRefs"`
	EntityRefs             []string      `bson:"entityRefs"`
	AuthorID               string        `bson:"authorId"`
	ChannelID              string        `bson:"channelId"`
	RecallPath             string        `bson:"recallPath"`
	ContentVertical        string        `bson:"contentVertical"`
	SupplySource           string        `bson:"supplySource"`
	IntersectionDimension  string        `bson:"intersectionDimension"`
	IntersectionTagRefs    []string      `bson:"intersectionTagRefs"`
	IntersectionID         string        `bson:"intersectionId"`
	IntersectionClass      string        `bson:"intersectionClass"`
	IntersectionSourceRef  string        `bson:"intersectionSourceRef"`
	IntersectionEvidenceID string        `bson:"intersectionEvidenceId"`
	OccurredAt             string        `bson:"occurredAt"`
	CreatedAt              time.Time     `bson:"createdAt"`
}

type checkpointDocument struct {
	ID             string        `bson:"_id"`
	LastID         bson.ObjectID `bson:"lastId"`
	LeaseOwner     string        `bson:"leaseOwner"`
	LeaseExpiresAt time.Time     `bson:"leaseExpiresAt"`
}

type StreamRelay struct {
	events      *mongo.Collection
	checkpoints *mongo.Collection
	transport   redisruntime.Client
	consumer    string
	leaseOwner  string
	leaseTTL    time.Duration
	watermark   time.Duration

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewStreamRelay(db *mongo.Database, transport redisruntime.Client) *StreamRelay {
	return &StreamRelay{
		events:      db.Collection("rm_behavior_events"),
		checkpoints: db.Collection(behaviorCheckpointCollection),
		transport:   transport,
		consumer:    behaviorStreamConsumer,
		leaseOwner:  newLeaseOwner(),
		leaseTTL:    defaultLeaseTTL,
		watermark:   defaultWatermarkLag,
	}
}

func (r *StreamRelay) WithWatermarkLag(lag time.Duration) *StreamRelay {
	if lag < 0 {
		lag = 0
	}
	r.watermark = lag
	return r
}

func (r *StreamRelay) WithConsumer(consumer string) *StreamRelay {
	if value := strings.TrimSpace(consumer); value != "" {
		r.consumer = value
	}
	return r
}

func (r *StreamRelay) acquireLease(ctx context.Context) (bool, error) {
	now := time.Now().UTC()
	result, err := r.checkpoints.UpdateOne(
		ctx,
		bson.M{
			"_id": r.consumer,
			"$or": []bson.M{
				{"leaseOwner": r.leaseOwner},
				{"leaseExpiresAt": bson.M{"$exists": false}},
				{"leaseExpiresAt": bson.M{"$lte": now}},
			},
		},
		bson.M{"$set": bson.M{
			"leaseOwner":     r.leaseOwner,
			"leaseExpiresAt": now.Add(r.leaseTTL),
			"updatedAt":      now,
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf("acquire content behavior stream lease: %w", err)
	}
	return result.MatchedCount == 1 || result.UpsertedCount == 1, nil
}

func (r *StreamRelay) Drain(ctx context.Context, limit int) (int, error) {
	if r == nil || r.events == nil || r.checkpoints == nil || r.transport == nil {
		return 0, errors.New("content behavior stream relay is not configured")
	}
	if limit <= 0 || limit > 1000 {
		limit = 200
	}
	acquired, err := r.acquireLease(ctx)
	if err != nil || !acquired {
		return 0, err
	}
	var checkpoint checkpointDocument
	err = r.checkpoints.FindOne(ctx, bson.M{"_id": r.consumer}).Decode(&checkpoint)
	if err != nil {
		return 0, fmt.Errorf("load content behavior stream checkpoint: %w", err)
	}
	bounds := bson.M{}
	if !checkpoint.LastID.IsZero() {
		bounds["$gt"] = checkpoint.LastID
	}
	if r.watermark > 0 {
		bounds["$lt"] = bson.NewObjectIDFromTimestamp(time.Now().UTC().Add(-r.watermark))
	}
	filter := bson.M{}
	if len(bounds) > 0 {
		filter["_id"] = bounds
	}
	cursor, err := r.events.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return 0, fmt.Errorf("scan ContentBehaviorFact: %w", err)
	}
	defer cursor.Close(ctx)
	var rows []BehaviorFactDocument
	if err := cursor.All(ctx, &rows); err != nil {
		return 0, fmt.Errorf("decode ContentBehaviorFact: %w", err)
	}
	processed := 0
	for _, row := range rows {
		values, buildErr := BuildStreamValues(row)
		if buildErr != nil {
			return processed, buildErr
		}
		if _, appendErr := r.transport.XAdd(ctx, BehaviorFactStream, values); appendErr != nil {
			return processed, fmt.Errorf("append ContentBehaviorFact stream: %w", appendErr)
		}
		now := time.Now().UTC()
		result, updateErr := r.checkpoints.UpdateOne(
			ctx,
			bson.M{
				"_id":            r.consumer,
				"leaseOwner":     r.leaseOwner,
				"leaseExpiresAt": bson.M{"$gt": now},
			},
			bson.M{"$set": bson.M{
				"lastId":         row.ID,
				"leaseExpiresAt": now.Add(r.leaseTTL),
				"updatedAt":      now,
			}},
		)
		if updateErr != nil || result.MatchedCount != 1 {
			if updateErr == nil {
				updateErr = errors.New("content behavior stream lease lost")
			}
			return processed, fmt.Errorf("commit ContentBehaviorFact checkpoint: %w", updateErr)
		}
		processed++
	}
	if len(rows) > 0 {
		if err := r.transport.XTrimOlderThan(ctx, BehaviorFactStream, behaviorStreamRetention); err != nil {
			return processed, fmt.Errorf("trim ContentBehaviorFact stream: %w", err)
		}
		if err := r.transport.Expire(ctx, BehaviorFactStream, behaviorStreamRetention); err != nil {
			return processed, fmt.Errorf("expire ContentBehaviorFact stream: %w", err)
		}
	}
	return processed, nil
}

// BuildStreamValues encodes the canonical cross-context envelope without
// exposing the source Mongo ObjectID as the business event identity.
func BuildStreamValues(row BehaviorFactDocument) (map[string]string, error) {
	clientEventID := strings.TrimSpace(row.ClientEventID)
	subjectID := strings.TrimSpace(row.UserID)
	if subjectID == "" {
		subjectID = strings.TrimSpace(row.DeviceActorID)
	}
	if clientEventID == "" || subjectID == "" || strings.TrimSpace(row.Action) == "" || row.ID.IsZero() {
		return nil, errors.New("ContentBehaviorFact identity is incomplete")
	}
	eventDigest := sha256.Sum256([]byte("ContentBehaviorRecorded:" + subjectID + ":" + clientEventID))
	payload, err := json.Marshal(map[string]any{
		"clientEventId":          clientEventID,
		"personaId":              strings.TrimSpace(row.UserID),
		"deviceActorId":          strings.TrimSpace(row.DeviceActorID),
		"sessionId":              strings.TrimSpace(row.SessionID),
		"contentId":              strings.TrimSpace(row.ContentID),
		"contentType":            strings.TrimSpace(row.ContentType),
		"action":                 strings.TrimSpace(row.Action),
		"state":                  strings.TrimSpace(row.State),
		"duration":               row.Duration,
		"feedRequestId":          strings.TrimSpace(row.FeedRequestID),
		"tagRefs":                row.Tags,
		"entityRefs":             row.EntityRefs,
		"authorId":               strings.TrimSpace(row.AuthorID),
		"channelId":              strings.TrimSpace(row.ChannelID),
		"recallPath":             strings.TrimSpace(row.RecallPath),
		"contentVertical":        strings.TrimSpace(row.ContentVertical),
		"supplySource":           strings.TrimSpace(row.SupplySource),
		"intersectionDimension":  strings.TrimSpace(row.IntersectionDimension),
		"intersectionTagRefs":    row.IntersectionTagRefs,
		"intersectionId":         strings.TrimSpace(row.IntersectionID),
		"intersectionClass":      strings.TrimSpace(row.IntersectionClass),
		"intersectionSourceRef":  strings.TrimSpace(row.IntersectionSourceRef),
		"intersectionEvidenceId": strings.TrimSpace(row.IntersectionEvidenceID),
		"occurredAt":             strings.TrimSpace(row.OccurredAt),
	})
	if err != nil {
		return nil, fmt.Errorf("encode ContentBehaviorFact stream payload: %w", err)
	}
	return map[string]string{
		"eventId":        hex.EncodeToString(eventDigest[:]),
		"eventName":      "ContentBehaviorRecorded",
		"sourceSequence": row.ID.Hex(),
		"subjectId":      subjectID,
		"feedRequestId":  strings.TrimSpace(row.FeedRequestID),
		"targetId":       strings.TrimSpace(row.ContentID),
		"payload":        string(payload),
		"occurredAt":     strings.TrimSpace(row.OccurredAt),
	}, nil
}

func (r *StreamRelay) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		_, err := r.Drain(ctx, 200)
		if err != nil {
			r.recordFailure(err)
		} else {
			r.recordSuccess()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (r *StreamRelay) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 30 * time.Second
	}
	r.mu.RLock()
	defer r.mu.RUnlock()
	if r.lastSuccess.IsZero() {
		return errors.New("content behavior stream relay has not completed a scan")
	}
	if r.lastFailure != nil {
		return fmt.Errorf("content behavior stream relay failed: %w", r.lastFailure)
	}
	if time.Since(r.lastSuccess) > maxStaleness {
		return errors.New("content behavior stream relay heartbeat is stale")
	}
	return nil
}

func (r *StreamRelay) recordSuccess() {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastSuccess = time.Now().UTC()
	r.lastFailure = nil
}

func (r *StreamRelay) recordFailure(err error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.lastFailure = err
}

func newLeaseOwner() string {
	var value [16]byte
	if _, err := rand.Read(value[:]); err == nil {
		return "content-behavior-stream-" + hex.EncodeToString(value[:])
	}
	return fmt.Sprintf("content-behavior-stream-%d", time.Now().UnixNano())
}

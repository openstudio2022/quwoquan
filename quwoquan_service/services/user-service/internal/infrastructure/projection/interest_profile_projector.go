// Package projection hosts user-domain read-model projectors that consume
// cross-service events and maintain user-owned read models, plus the readers
// that serve those read models to adapters.
package projection

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/user-service/internal/application"
)

// InterestChannel is the Redis Pub/Sub channel content-service publishes the
// derived interest profile on (RedisEventPublisher → events.content.{type}).
const InterestChannel = "events.content.UserInterestRecomputed"

// userProfileViewCollection is the user-domain interest read model. NOTE: the
// rm_ prefix is the canonical collection name (the earlier runtime skeleton in
// runtime/projector/readmodels.go wrote an unprefixed name and was never wired;
// it has been removed and this package is the single owner of the read model).
const userProfileViewCollection = "rm_user_profile_view"

// interestEventEnvelope is the cross-service envelope shape published by
// content-service's RedisEventPublisher.
type interestEventEnvelope struct {
	Payload struct {
		Type        string `json:"type"`
		AggregateID string `json:"aggregateId"`
		Data        struct {
			UserID          string          `json:"userId"`
			InterestProfile json.RawMessage `json:"interestProfile"`
			Segments        []string        `json:"segments"`
		} `json:"data"`
		OccurredAt string `json:"occurredAt"`
	} `json:"payload"`
}

// ParseInterestEvent extracts the user id, derived profile, and segment
// memberships from a raw envelope JSON. Pure function: unit-testable without
// Redis or Mongo.
func ParseInterestEvent(raw string) (string, application.InterestProfileView, []string, error) {
	var env interestEventEnvelope
	if err := json.Unmarshal([]byte(raw), &env); err != nil {
		return "", application.InterestProfileView{}, nil, fmt.Errorf("decode envelope: %w", err)
	}
	userID := env.Payload.Data.UserID
	if userID == "" {
		userID = env.Payload.AggregateID
	}
	var profile application.InterestProfileView
	if len(env.Payload.Data.InterestProfile) > 0 {
		if err := json.Unmarshal(env.Payload.Data.InterestProfile, &profile); err != nil {
			return "", application.InterestProfileView{}, nil, fmt.Errorf("decode interestProfile: %w", err)
		}
	}
	return userID, profile, env.Payload.Data.Segments, nil
}

// InterestProfileProjector consumes UserInterestRecomputed and maintains
// rm_user_profile_view.interestProfile (single source of truth in user domain).
type InterestProfileProjector struct {
	coll   *mongo.Collection
	logger *slog.Logger
}

func NewInterestProfileProjector(db *mongo.Database, logger *slog.Logger) *InterestProfileProjector {
	if logger == nil {
		logger = slog.Default()
	}
	return &InterestProfileProjector{
		coll:   db.Collection(userProfileViewCollection),
		logger: logger,
	}
}

// Run subscribes the interest channel and projects until ctx is cancelled.
func (p *InterestProfileProjector) Run(ctx context.Context, redis rtredis.Client) error {
	sub, err := redis.Subscribe(ctx, InterestChannel)
	if err != nil {
		return fmt.Errorf("subscribe %s: %w", InterestChannel, err)
	}
	defer func() { _ = sub.Close() }()
	p.logger.Info("interest profile projector started", "channel", InterestChannel)

	ch := sub.Channel()
	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case msg, ok := <-ch:
			if !ok {
				return nil
			}
			if err := p.handle(ctx, msg.Payload); err != nil {
				p.logger.Warn("interest profile projection failed", "err", err)
			}
		}
	}
}

func (p *InterestProfileProjector) handle(ctx context.Context, raw string) error {
	userID, profile, segments, err := ParseInterestEvent(raw)
	if err != nil {
		interestProjectionTotal.WithLabelValues("parse_error").Inc()
		return err
	}
	if userID == "" {
		return nil
	}
	if segments == nil {
		segments = []string{}
	}
	_, err = p.coll.UpdateOne(ctx,
		bson.M{"_id": userID},
		bson.M{"$set": bson.M{
			"interestProfile": profile,
			"segments":        segments,
			"updatedAt":       time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		interestProjectionTotal.WithLabelValues("write_error").Inc()
		return fmt.Errorf("upsert interest profile for %s: %w", userID, err)
	}
	interestProjectionTotal.WithLabelValues("ok").Inc()
	if !profile.RecomputedAt.IsZero() {
		if lag := time.Since(profile.RecomputedAt).Seconds(); lag >= 0 {
			interestFreshnessLag.Observe(lag)
		}
	}
	return nil
}

// MongoInterestProfileReader serves rm_user_profile_view.interestProfile reads.
// It implements application.InterestProfileReader.
type MongoInterestProfileReader struct {
	coll *mongo.Collection
}

func NewMongoInterestProfileReader(db *mongo.Database) *MongoInterestProfileReader {
	return &MongoInterestProfileReader{coll: db.Collection(userProfileViewCollection)}
}

// GetInterestProfile returns the derived profile plus segment memberships, or
// nil when no read model has been projected for the user yet.
func (r *MongoInterestProfileReader) GetInterestProfile(ctx context.Context, userID string) (*application.InterestProfileView, error) {
	var doc struct {
		InterestProfile *application.InterestProfileView `bson:"interestProfile"`
		Segments        []string                         `bson:"segments"`
	}
	err := r.coll.FindOne(ctx, bson.M{"_id": userID}).Decode(&doc)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	view := doc.InterestProfile
	if view == nil {
		view = &application.InterestProfileView{}
	}
	view.Segments = doc.Segments
	return view, nil
}

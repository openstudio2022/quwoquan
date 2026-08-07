package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	quotagenerated "quwoquan_service/services/content-service/generated/media/original_access_quota"
	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

// MongoStore exclusively owns the OriginalAccessQuota window counters and the
// reservation receipts that make a reservation exactly-once per idempotency key.
type MongoStore struct {
	quotas       *mongo.Collection
	reservations *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("OriginalAccessQuota MongoStore requires database")
	}
	return &MongoStore{
		quotas:       database.Collection("media_original_access_rate_limits"),
		reservations: database.Collection("media_original_access_quota_reservations"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.quotas.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "windowExpiresAt", Value: 1}},
		Options: options.Index().SetName("idx_media_original_access_rate_limit_expire").SetExpireAfterSeconds(0),
	}); err != nil {
		return err
	}
	_, err := store.reservations.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "windowExpiresAt", Value: 1}},
		Options: options.Index().SetName("idx_media_original_access_quota_reservation_expire").SetExpireAfterSeconds(0),
	})
	return err
}

type originalAccessQuotaReservationDocument struct {
	IdempotencyKey  string    `bson:"_id"`
	CommandDigest   string    `bson:"commandDigest"`
	QuotaID         string    `bson:"quotaId"`
	ViewerID        string    `bson:"viewerId"`
	AssetID         string    `bson:"assetId"`
	Purpose         string    `bson:"purpose"`
	WindowStartedAt time.Time `bson:"windowStartedAt"`
	WindowExpiresAt time.Time `bson:"windowExpiresAt"`
	GrantExpiresAt  time.Time `bson:"grantExpiresAt"`
}

func (store *MongoStore) Reserve(
	ctx context.Context,
	requested quotamodel.Reservation,
	policy quotamodel.Policy,
) (quotaports.ReserveResult, error) {
	if err := requested.Validate(); err != nil {
		return quotaports.ReserveResult{}, err
	}
	if !policy.IsValid() {
		return quotaports.ReserveResult{}, errors.New(
			"original access quota reservation requires a valid policy",
		)
	}
	if replayed, found, err := store.findReservation(
		ctx,
		requested.IdempotencyKey,
		requested.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	session, err := store.quotas.Database().Client().StartSession()
	if err != nil {
		return quotaports.ReserveResult{}, err
	}
	defer session.EndSession(ctx)
	result := quotaports.ReserveResult{Reservation: requested}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if replayed, found, findErr := store.findReservation(
			txCtx,
			requested.IdempotencyKey,
			requested.CommandDigest,
		); findErr != nil {
			return nil, findErr
		} else if found {
			result = replayed
			return nil, nil
		}
		if consumeErr := store.consumeWindowSlot(txCtx, requested, policy); consumeErr != nil {
			return nil, consumeErr
		}
		_, insertErr := store.reservations.InsertOne(txCtx, originalAccessQuotaReservationDocument{
			IdempotencyKey:  requested.IdempotencyKey,
			CommandDigest:   requested.CommandDigest,
			QuotaID:         requested.QuotaID,
			ViewerID:        requested.ViewerID,
			AssetID:         requested.AssetID,
			Purpose:         requested.Purpose,
			WindowStartedAt: requested.WindowStartedAt.UTC(),
			WindowExpiresAt: requested.WindowExpiresAt.UTC(),
			GrantExpiresAt:  requested.GrantExpiresAt.UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		if replayed, found, replayErr := store.findReservation(
			ctx,
			requested.IdempotencyKey,
			requested.CommandDigest,
		); replayErr == nil && found {
			return replayed, nil
		}
		return quotaports.ReserveResult{}, err
	}
	return result, nil
}

// consumeWindowSlot increments the window counter only while it is strictly
// below maxGrants. The conditional filter plus upsert makes an exhausted
// window surface as a duplicate key on the quota identity.
func (store *MongoStore) consumeWindowSlot(
	ctx context.Context,
	requested quotamodel.Reservation,
	policy quotamodel.Policy,
) error {
	_, err := store.quotas.UpdateOne(
		ctx,
		bson.D{
			{Key: "_id", Value: requested.QuotaID},
			{Key: "grantCount", Value: bson.D{{Key: "$lt", Value: policy.MaxGrants}}},
		},
		bson.D{
			{Key: "$inc", Value: bson.D{{Key: "grantCount", Value: 1}}},
			{Key: "$setOnInsert", Value: bson.D{
				{Key: "viewerId", Value: requested.ViewerID},
				{Key: "assetId", Value: requested.AssetID},
				{Key: "purpose", Value: requested.Purpose},
				{Key: "windowStartedAt", Value: requested.WindowStartedAt.UTC()},
				{Key: "windowExpiresAt", Value: requested.WindowExpiresAt.UTC()},
				{Key: "maxGrants", Value: policy.MaxGrants},
				{Key: "grantTtlSeconds", Value: int(policy.GrantTTL / time.Second)},
			}},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return quotagenerated.AppErrorFromOriginalAccessRateLimited(
			"media original access rate limit exhausted",
		)
	}
	return err
}

func (store *MongoStore) findReservation(
	ctx context.Context,
	idempotencyKey string,
	commandDigest string,
) (quotaports.ReserveResult, bool, error) {
	var document originalAccessQuotaReservationDocument
	err := store.reservations.FindOne(
		ctx,
		bson.D{{Key: "_id", Value: strings.TrimSpace(idempotencyKey)}},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return quotaports.ReserveResult{}, false, nil
	}
	if err != nil {
		return quotaports.ReserveResult{}, false, err
	}
	if document.CommandDigest != strings.TrimSpace(commandDigest) {
		return quotaports.ReserveResult{}, false, contentgenerated.AppErrorFromIdempotencyConflict(
			"original access quota idempotency key reused with another command",
		)
	}
	return quotaports.ReserveResult{
		Reservation: quotamodel.Reservation{
			QuotaID:         document.QuotaID,
			IdempotencyKey:  document.IdempotencyKey,
			CommandDigest:   document.CommandDigest,
			ViewerID:        document.ViewerID,
			AssetID:         document.AssetID,
			Purpose:         document.Purpose,
			WindowStartedAt: document.WindowStartedAt.UTC(),
			WindowExpiresAt: document.WindowExpiresAt.UTC(),
			GrantExpiresAt:  document.GrantExpiresAt.UTC(),
		},
		Replayed: true,
	}, true, nil
}

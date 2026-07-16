package provider

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/runtime/otpseal"
)

const otpCodeReferenceCollection = "otp_code_reference_vault"

type MongoOTPCodeReferenceStore struct {
	collection *mongo.Collection
}

type otpCodeReferenceDocument struct {
	RequestID   string    `bson:"_id"`
	ChallengeID string    `bson:"challengeId"`
	CodeRef     string    `bson:"codeRef"`
	ExpiresAt   time.Time `bson:"expiresAt"`
	UpdatedAt   time.Time `bson:"updatedAt"`
}

func NewMongoOTPCodeReferenceStore(database *mongo.Database) *MongoOTPCodeReferenceStore {
	return &MongoOTPCodeReferenceStore{collection: database.Collection(otpCodeReferenceCollection)}
}

func (s *MongoOTPCodeReferenceStore) EnsureIndexes(ctx context.Context) error {
	_, err := s.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("ttl_otp_code_reference").SetExpireAfterSeconds(0),
		},
		{
			Keys:    bson.D{{Key: "challengeId", Value: 1}},
			Options: options.Index().SetName("idx_otp_code_reference_challenge"),
		},
	})
	if err != nil {
		return fmt.Errorf("create otp code reference indexes: %w", err)
	}
	return nil
}

func (s *MongoOTPCodeReferenceStore) Put(ctx context.Context, reference otpseal.StoredReference) error {
	if s == nil || s.collection == nil ||
		strings.TrimSpace(reference.RequestID) == "" ||
		strings.TrimSpace(reference.ChallengeID) == "" ||
		strings.TrimSpace(reference.CodeRef) == "" ||
		reference.ExpiresAt.IsZero() {
		return otpseal.ErrInvalidReference
	}
	_, err := s.collection.UpdateOne(
		ctx,
		bson.M{"_id": reference.RequestID, "challengeId": reference.ChallengeID},
		bson.M{
			"$set": bson.M{
				"challengeId": reference.ChallengeID,
				"codeRef":     reference.CodeRef,
				"expiresAt":   reference.ExpiresAt.UTC(),
				"updatedAt":   time.Now().UTC(),
			},
			"$setOnInsert": bson.M{"_id": reference.RequestID},
		},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func (s *MongoOTPCodeReferenceStore) Get(ctx context.Context, requestID, challengeID string) (otpseal.StoredReference, error) {
	if s == nil || s.collection == nil {
		return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
	}
	var document otpCodeReferenceDocument
	err := s.collection.FindOne(ctx, bson.M{
		"_id":         strings.TrimSpace(requestID),
		"challengeId": strings.TrimSpace(challengeID),
		"expiresAt":   bson.M{"$gt": time.Now().UTC()},
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
	}
	if err != nil {
		return otpseal.StoredReference{}, err
	}
	return otpseal.StoredReference{
		RequestID:   document.RequestID,
		ChallengeID: document.ChallengeID,
		CodeRef:     document.CodeRef,
		ExpiresAt:   document.ExpiresAt,
	}, nil
}

func (s *MongoOTPCodeReferenceStore) Delete(ctx context.Context, requestID, challengeID string) error {
	if s == nil || s.collection == nil {
		return nil
	}
	_, err := s.collection.DeleteOne(ctx, bson.M{
		"_id":         strings.TrimSpace(requestID),
		"challengeId": strings.TrimSpace(challengeID),
	})
	return err
}

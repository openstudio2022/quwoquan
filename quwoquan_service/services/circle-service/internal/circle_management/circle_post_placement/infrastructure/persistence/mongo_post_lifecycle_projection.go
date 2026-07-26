package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/circle-service/internal/circle_management/circle/application"
	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

const (
	contentPostInboxCollection   = "circle_content_post_inbox"
	contentPostFailureCollection = "circle_content_post_failures"
)

type MongoPostLifecycleProjection struct {
	views          *mongo.Collection
	inbox          *mongo.Collection
	failures       *mongo.Collection
	closedSubjects *mongo.Collection
}

func NewMongoPostLifecycleProjection(database *mongo.Database) *MongoPostLifecycleProjection {
	if database == nil {
		panic("Circle Post lifecycle projection requires database")
	}
	return &MongoPostLifecycleProjection{
		views:          database.Collection(postOwnerProjectionCollection),
		inbox:          database.Collection(contentPostInboxCollection),
		failures:       database.Collection(contentPostFailureCollection),
		closedSubjects: database.Collection("circle_closed_account_subjects"),
	}
}

func (projection *MongoPostLifecycleProjection) EnsureIndexes(ctx context.Context) error {
	if _, err := projection.views.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "state", Value: 1}, {Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_circle_post_owner_view_state"),
	}); err != nil {
		return err
	}
	_, err := projection.failures.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "updatedAt", Value: 1}}, Options: options.Index().SetName("idx_circle_content_post_failure_updated"),
	})
	return err
}

func (projection *MongoPostLifecycleProjection) ApplyPostLifecycle(ctx context.Context, event placementports.PostLifecycleEvent) error {
	if projection == nil || projection.views == nil || projection.inbox == nil {
		return fmt.Errorf("Circle Post lifecycle projection is not configured")
	}
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		strings.TrimSpace(event.PostID) == "" || event.PostVersion <= 0 || event.OccurredAt.IsZero() {
		return fmt.Errorf("Content Post lifecycle event identity is incomplete")
	}
	if applied, err := projection.postEventApplied(ctx, event.EventID); err != nil || applied {
		return err
	}
	session, err := projection.views.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if applied, findErr := projection.postEventApplied(txCtx, event.EventID); findErr != nil || applied {
			return nil, findErr
		}
		if applyErr := projection.applyPostView(txCtx, event); applyErr != nil {
			return nil, applyErr
		}
		_, insertErr := projection.inbox.InsertOne(txCtx, bson.M{
			"_id": event.EventID, "postId": event.PostID,
			"postVersion": event.PostVersion, "appliedAt": time.Now().UTC(),
		})
		return nil, insertErr
	})
	if err == nil {
		return nil
	}
	if applied, findErr := projection.postEventApplied(ctx, event.EventID); findErr == nil && applied {
		return nil
	}
	return err
}

func (projection *MongoPostLifecycleProjection) applyPostView(ctx context.Context, event placementports.PostLifecycleEvent) error {
	switch event.EventType {
	case "PostCreated", "PostPublished", "PostUpdated", "PostSettingsUpdated",
		"PostPromotedToWork", "PostDeleted", "PostPrivacyRedacted", "PostPurged":
		// These facts can change the minimal Post external reference.
	default:
		// Other Post facts are deliberately acknowledged into the inbox but do
		// not grow Circle's external-reference model.
		return nil
	}
	var current struct {
		OwnerPersonaID string `bson:"ownerPersonaId"`
		State          string `bson:"state"`
		PostVersion    int64  `bson:"postVersion"`
	}
	err := projection.views.FindOne(ctx, bson.M{"_id": event.PostID}).Decode(&current)
	found := err == nil
	if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
		return err
	}
	if found && current.PostVersion >= event.PostVersion {
		return nil
	}
	if event.EventType == "PostPurged" {
		if !found {
			return nil
		}
		result, deleteErr := projection.views.DeleteOne(ctx, bson.M{"_id": event.PostID, "postVersion": current.PostVersion})
		if deleteErr != nil {
			return deleteErr
		}
		if result.DeletedCount != 1 {
			return fmt.Errorf("Post owner view version changed during purge")
		}
		return nil
	}
	ownerPersonaID := strings.TrimSpace(event.OwnerPersonaID)
	if ownerPersonaID == "" && found {
		ownerPersonaID = current.OwnerPersonaID
	}
	if ownerPersonaID == "" {
		return fmt.Errorf("Content Post lifecycle event %q has no owner persona", event.EventID)
	}
	closed, err := projection.isClosedAccountSubject(ctx, ownerPersonaID)
	if err != nil {
		return err
	}
	if closed {
		if !found {
			return nil
		}
		_, err := projection.views.DeleteOne(
			ctx,
			bson.M{"_id": event.PostID},
		)
		return err
	}
	state := strings.TrimSpace(event.State)
	if state == "" && found {
		state = current.State
	}
	switch event.EventType {
	case "PostCreated":
		if state == "" {
			state = "draft"
		}
	case "PostPublished":
		state = "published"
	case "PostDeleted":
		state = "deleted"
	case "PostPrivacyRedacted":
		state = "redacted"
	}
	if state == "" {
		state = "draft"
	}
	document := bson.M{
		"_id": event.PostID, "ownerPersonaId": ownerPersonaID, "state": state,
		"postVersion": event.PostVersion, "updatedAt": event.OccurredAt.UTC(),
	}
	if !found {
		_, insertErr := projection.views.InsertOne(ctx, document)
		return insertErr
	}
	result, replaceErr := projection.views.ReplaceOne(ctx,
		bson.M{"_id": event.PostID, "postVersion": current.PostVersion}, document)
	if replaceErr != nil {
		return replaceErr
	}
	if result.MatchedCount != 1 {
		return fmt.Errorf("Post owner view version changed during projection")
	}
	return nil
}

func (projection *MongoPostLifecycleProjection) isClosedAccountSubject(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	err := projection.closedSubjects.FindOne(
		ctx,
		bson.M{
			"_id": application.UserAccountClosedSubjectID(subjectID),
		},
		options.FindOne().SetProjection(bson.M{"_id": 1}),
	).Err()
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, fmt.Errorf(
			"read Circle closed-account subject tombstone: %w",
			err,
		)
	}
	return true, nil
}

func (projection *MongoPostLifecycleProjection) RecordPostLifecycleFailure(ctx context.Context, streamID, eventID string, cause error) (int64, error) {
	if cause == nil || strings.TrimSpace(streamID) == "" {
		return 0, fmt.Errorf("Post lifecycle failure identity and cause are required")
	}
	message := cause.Error()
	if len(message) > 1024 {
		message = message[:1024]
	}
	var document struct {
		Attempts int64 `bson:"attempts"`
	}
	err := projection.failures.FindOneAndUpdate(ctx,
		bson.M{"_id": strings.TrimSpace(streamID)},
		bson.M{
			"$inc": bson.M{"attempts": int64(1)},
			"$set": bson.M{"eventId": strings.TrimSpace(eventID), "lastError": message, "updatedAt": time.Now().UTC()},
		},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&document)
	if err != nil {
		return 0, err
	}
	return document.Attempts, nil
}

func (projection *MongoPostLifecycleProjection) ClearPostLifecycleFailure(ctx context.Context, streamID string) error {
	_, err := projection.failures.DeleteOne(ctx, bson.M{"_id": strings.TrimSpace(streamID)})
	return err
}

func (projection *MongoPostLifecycleProjection) postEventApplied(ctx context.Context, eventID string) (bool, error) {
	err := projection.inbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID)}).Err()
	if errors.Is(err, mongo.ErrNoDocuments) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}

var (
	_ placementports.PostLifecycleProjection   = (*MongoPostLifecycleProjection)(nil)
	_ placementports.PostLifecycleFailureStore = (*MongoPostLifecycleProjection)(nil)
)

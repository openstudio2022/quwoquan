// Package projection 清理 UserAccountClosed 后的 user-service Mongo 派生数据。
package projection

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/user-service/internal/application"
	userevent "quwoquan_service/services/user-service/internal/domain/user/event"
)

// MongoCleanupProjector 的每一步都幂等；任一步失败会让
// UserAccountClosed durable outbox 保持 pending 并重放。
type MongoCleanupProjector struct {
	profileViews      *mongo.Collection
	followingSubjects *mongo.Collection
	visitStates       *mongo.Collection
	creatorProfiles   *mongo.Collection
}

var _ application.UserEventPublisher = (*MongoCleanupProjector)(nil)

func NewMongoCleanupProjector(db *mongo.Database) *MongoCleanupProjector {
	if db == nil {
		return &MongoCleanupProjector{}
	}
	return &MongoCleanupProjector{
		profileViews:      db.Collection("rm_user_profile_view"),
		followingSubjects: db.Collection("following_subjects"),
		visitStates:       db.Collection("followed_subject_visit_states"),
		creatorProfiles:   db.Collection("creator_runtime_profiles"),
	}
}

func (projector *MongoCleanupProjector) PublishUserEvent(
	ctx context.Context,
	eventType string,
	accountID string,
	_ string,
	payload map[string]any,
) error {
	if eventType != userevent.UserAccountClosed ||
		projector == nil ||
		projector.profileViews == nil {
		return nil
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return nil
	}
	personaIDs := closedPersonaIDs(payload)
	closedAt := closedEventTime(payload)

	if _, err := projector.profileViews.DeleteOne(
		ctx,
		bson.M{"_id": accountID},
	); err != nil {
		return fmt.Errorf("delete closed account interest projection: %w", err)
	}
	if len(personaIDs) == 0 {
		return nil
	}
	subjectIDs := append([]string{accountID}, personaIDs...)
	if _, err := projector.followingSubjects.DeleteMany(ctx, bson.M{
		"$or": bson.A{
			bson.M{"viewerSubAccountId": bson.M{"$in": personaIDs}},
			bson.M{
				"subjectType": "user",
				"subjectId":   bson.M{"$in": subjectIDs},
			},
		},
	}); err != nil {
		return fmt.Errorf("delete closed persona following projections: %w", err)
	}
	if _, err := projector.visitStates.DeleteMany(ctx, bson.M{
		"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": personaIDs}},
			bson.M{
				"subjectType": "user",
				"subjectId":   bson.M{"$in": subjectIDs},
			},
		},
	}); err != nil {
		return fmt.Errorf("delete closed persona visit projections: %w", err)
	}
	if _, err := projector.creatorProfiles.UpdateMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"subAccountId": bson.M{"$in": personaIDs}},
			bson.M{"creatorId": bson.M{"$in": personaIDs}},
		}},
		bson.M{
			"$set": bson.M{
				"status":       "tombstoned",
				"displayName":  "已注销用户",
				"tombstonedAt": closedAt,
				"updatedAt":    closedAt,
			},
			"$unset": creatorProfilePIIUnset(),
		},
	); err != nil {
		return fmt.Errorf("tombstone closed creator projections: %w", err)
	}
	return nil
}

func closedPersonaIDs(payload map[string]any) []string {
	if payload == nil {
		return nil
	}
	seen := map[string]struct{}{}
	result := make([]string, 0)
	appendID := func(value string) {
		value = strings.TrimSpace(value)
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	switch values := payload["personaIds"].(type) {
	case []string:
		for _, value := range values {
			appendID(value)
		}
	case []any:
		for _, value := range values {
			if text, ok := value.(string); ok {
				appendID(text)
			}
		}
	}
	return result
}

func closedEventTime(payload map[string]any) time.Time {
	if payload != nil {
		if raw, ok := payload["updatedAt"].(string); ok {
			if parsed, err := time.Parse(time.RFC3339Nano, raw); err == nil {
				return parsed.UTC()
			}
		}
	}
	return time.Unix(0, 0).UTC()
}

func creatorProfilePIIUnset() bson.M {
	return bson.M{
		"handle":                    "",
		"headline":                  "",
		"bio":                       "",
		"slogan":                    "",
		"avatarUrl":                 "",
		"avatarObjectKey":           "",
		"avatarSha256":              "",
		"coverUrl":                  "",
		"coverObjectKey":            "",
		"coverSha256":               "",
		"tagRefs":                   "",
		"publicProfileTagRefs":      "",
		"roles":                     "",
		"verticals":                 "",
		"segment":                   "",
		"preferredContentTypes":     "",
		"creatorArchetype":          "",
		"carrierAffinity":           "",
		"preferredBlueprintIds":     "",
		"coverageScope":             "",
		"claimPolicy":               "",
		"expertiseClaims":           "",
		"mustNotClaim":              "",
		"disclosure":                "",
		"entityRefs":                "",
		"circleRefs":                "",
		"sourceStatus":              "",
		"works":                     "",
		"packageDigest":             "",
		"releaseId":                 "",
		"managedBy":                 "",
		"importedAt":                "",
		"preferredBlueprintVersion": "",
	}
}

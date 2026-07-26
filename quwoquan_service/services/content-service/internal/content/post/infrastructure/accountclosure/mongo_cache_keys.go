package accountclosure

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const recommendationCacheDayWindow = 8

type behaviorCacheIdentity struct {
	UserID        string `bson:"userId"`
	SessionID     string `bson:"sessionId"`
	ClientEventID string `bson:"clientEventId"`
	ContentID     string `bson:"contentId"`
}

func (store *MongoStore) PersonalCacheKeys(
	ctx context.Context,
	event UserAccountClosedEvent,
) ([]string, error) {
	if err := event.Validate(); err != nil {
		return nil, err
	}
	subjectIDs := event.SubjectIDs()
	keys := make([]string, 0, len(subjectIDs)*32)
	now := time.Now().UTC()
	for _, subjectID := range subjectIDs {
		keys = append(keys, fixedPersonalCacheKeys(subjectID)...)
		keys = append(keys, recommendationDayKeys(subjectID, now)...)
		keys = append(
			keys,
			recommendationDayKeys(subjectID, event.Payload.UpdatedAt.UTC())...,
		)
	}

	cursor, err := store.db.Collection("rm_behavior_events").Find(
		ctx,
		bson.M{"userId": bson.M{"$in": subjectIDs}},
		options.Find().SetProjection(bson.M{
			"userId":        1,
			"sessionId":     1,
			"clientEventId": 1,
			"contentId":     1,
		}),
	)
	if err != nil {
		return nil, fmt.Errorf(
			"collect closed-account recommendation cache identities: %w",
			err,
		)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var identity behaviorCacheIdentity
		if err := cursor.Decode(&identity); err != nil {
			return nil, fmt.Errorf(
				"decode closed-account recommendation cache identity: %w",
				err,
			)
		}
		keys = append(keys, dynamicPersonalCacheKeys(identity)...)
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf(
			"scan closed-account recommendation cache identities: %w",
			err,
		)
	}
	return uniqueStrings(keys), nil
}

func fixedPersonalCacheKeys(subjectID string) []string {
	hashTag := "{" + strings.TrimSpace(subjectID) + "}"
	return []string{
		"rec:negative:" + hashTag,
		"rec:hidden_authors:" + hashTag,
		"rec:hidden_types:" + hashTag,
		"rec:icool:" + hashTag,
		"rec:ineg:" + hashTag,
		"ix:watermark:" + hashTag,
	}
}

func recommendationDayKeys(subjectID string, anchor time.Time) []string {
	if anchor.IsZero() {
		return nil
	}
	hashTag := "{" + strings.TrimSpace(subjectID) + "}"
	keys := make([]string, 0, (recommendationCacheDayWindow+1)*2)
	for daysAgo := 0; daysAgo <= recommendationCacheDayWindow; daysAgo++ {
		day := anchor.AddDate(0, 0, -daysAgo).UTC().Format("20060102")
		keys = append(
			keys,
			"rec:served:"+hashTag+":"+day,
			"rec:impressed:"+hashTag+":"+day,
		)
	}
	return keys
}

func dynamicPersonalCacheKeys(identity behaviorCacheIdentity) []string {
	userID := strings.TrimSpace(identity.UserID)
	if userID == "" {
		return nil
	}
	hashTag := "{" + userID + "}"
	keys := make([]string, 0, 3)
	sessionID := strings.TrimSpace(identity.SessionID)
	if sessionID == "" {
		sessionID = "default"
	}
	keys = append(
		keys,
		"rec:session_signals:"+hashTag+":"+sessionID,
		"rec:realtime_interest:"+hashTag+":"+sessionID,
	)
	if clientEventID := strings.TrimSpace(identity.ClientEventID); clientEventID != "" {
		keys = append(
			keys,
			"rec:event_dedup:"+hashTag+":"+clientEventID,
		)
	}
	if contentID := strings.TrimSpace(identity.ContentID); contentID != "" {
		keys = append(
			keys,
			"rec:imp_score:"+userID+":"+contentID,
		)
	}
	return keys
}

// Package tagindex keeps the shared tag-service object_tag_index projection in
// sync for user profile career and interest tags.
package tagindex

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/user-service/internal/application"
	event "quwoquan_service/services/user-service/internal/domain/user/event"
	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type ProfileReader interface {
	FindByID(ctx context.Context, userID string) (*model.UserProfile, error)
}

type Projector struct {
	coll   *mongo.Collection
	reader ProfileReader
}

var _ application.UserEventPublisher = (*Projector)(nil)

func NewProjector(coll *mongo.Collection, reader ProfileReader) *Projector {
	return &Projector{
		coll:   coll,
		reader: reader,
	}
}

func (p *Projector) PublishUserEvent(ctx context.Context, eventType, userID, _ string, payload map[string]any) error {
	if p == nil || p.coll == nil {
		return nil
	}
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return nil
	}
	switch eventType {
	case event.UserProfileUpdated, event.UserRegistered:
		return p.reconcile(ctx, userID, eventType, payload)
	case event.UserAccountClosed:
		_, err := p.coll.DeleteOne(
			ctx,
			bson.M{"objectId": userID, "objectType": "user"},
		)
		if err != nil {
			return fmt.Errorf("delete closed user tag index: %w", err)
		}
	default:
	}
	return nil
}

func (p *Projector) reconcile(
	ctx context.Context,
	userID, eventType string,
	payload map[string]any,
) error {
	tagRefs := profileTagRefsFromPayload(payload)
	if tagRefs == nil && p.reader != nil {
		profile, err := p.reader.FindByID(ctx, userID)
		if err != nil {
			return fmt.Errorf("user tag index read-back: %w", err)
		}
		if profile != nil {
			tagRefs = profileTagRefsFromIdentityTags(profile.IdentityTags)
		}
	}
	if tagRefs == nil {
		tagRefs = []string{}
	}
	now := time.Now().UTC()
	_, err := p.coll.UpdateOne(
		ctx,
		bson.M{"objectId": userID, "objectType": "user"},
		bson.M{
			"$set": bson.M{
				"objectId":   userID,
				"objectType": "user",
				"tagRefs":    tagRefs,
				"updatedAt":  now,
			},
			"$setOnInsert": bson.M{"createdAt": now},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("user tag index upsert: %w", err)
	}
	return nil
}

func profileTagRefsFromPayload(payload map[string]any) []string {
	if payload == nil {
		return nil
	}
	result := make([]string, 0, 8)
	if occupation, ok := payload["occupationTagRef"].(string); ok {
		result = appendProfileTagRef(result, occupation)
	}
	switch interests := payload["interestTagRefs"].(type) {
	case []string:
		for _, tagRef := range interests {
			result = appendProfileTagRef(result, tagRef)
		}
	case []any:
		for _, tagRef := range interests {
			result = appendProfileTagRef(result, fmt.Sprint(tagRef))
		}
	}
	return dedupeStrings(result)
}

func profileTagRefsFromIdentityTags(encoded string) []string {
	return dedupeStrings(profileTagRefs(parsePgTextArray(encoded)))
}

func profileTagRefs(tags []string) []string {
	result := make([]string, 0, len(tags))
	for _, tagRef := range tags {
		result = appendProfileTagRef(result, tagRef)
	}
	return result
}

func appendProfileTagRef(values []string, tagRef string) []string {
	trimmed := strings.TrimSpace(tagRef)
	if strings.HasPrefix(trimmed, "Audience/用户/职业/") ||
		strings.HasPrefix(trimmed, "Audience/用户/兴趣偏好/") {
		return append(values, trimmed)
	}
	return values
}

func dedupeStrings(values []string) []string {
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		text := strings.TrimSpace(value)
		if text == "" {
			continue
		}
		if _, ok := seen[text]; ok {
			continue
		}
		seen[text] = struct{}{}
		result = append(result, text)
	}
	return result
}

func parsePgTextArray(raw string) []string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || trimmed == "{}" {
		return []string{}
	}
	trimmed = strings.TrimPrefix(strings.TrimSuffix(trimmed, "}"), "{")
	if strings.TrimSpace(trimmed) == "" {
		return []string{}
	}
	parts := strings.Split(trimmed, ",")
	out := make([]string, 0, len(parts))
	for _, part := range parts {
		value := strings.Trim(strings.TrimSpace(part), `"`)
		value = strings.ReplaceAll(value, `\"`, `"`)
		if value != "" {
			out = append(out, value)
		}
	}
	return out
}

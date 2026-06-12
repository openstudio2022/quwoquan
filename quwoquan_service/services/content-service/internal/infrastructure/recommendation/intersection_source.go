package recommendation

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	rtrec "quwoquan_service/runtime/recommendation"
	app "quwoquan_service/services/content-service/internal/application"
)

type MongoIntersectionSource struct {
	social     *MongoSocialGraphProvider
	entityTags rtrec.EntityTagIndex
	candidates rtrec.SocialCandidateDB
}

func NewMongoIntersectionSource(
	social *MongoSocialGraphProvider,
	entityTags rtrec.EntityTagIndex,
	candidates rtrec.SocialCandidateDB,
) *MongoIntersectionSource {
	if entityTags == nil {
		entityTags = &rtrec.NullEntityTagIndex{}
	}
	if candidates == nil {
		candidates = &rtrec.NullSocialCandidateDB{}
	}
	return &MongoIntersectionSource{
		social:     social,
		entityTags: entityTags,
		candidates: candidates,
	}
}

func (s *MongoIntersectionSource) FactReasons(ctx context.Context, userID, channel string) ([]app.IntersectionReasonView, error) {
	now := time.Now().UTC()
	reasons := make([]app.IntersectionReasonView, 0, 3)

	if circleTags, err := s.socialCircleTags(ctx, userID); err == nil && len(circleTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			"interest",
			"circle_tags",
			"圈子兴趣",
			"你在圈子里常见这些主题",
			"circleTag",
			"view_object",
			circleTags,
			7*24*time.Hour,
		))
	}

	if friendTags, err := s.socialFriendTags(ctx, userID); err == nil && len(friendTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			"relationship",
			"friend_tags",
			"社交交集",
			"你关注的人也更常讨论这些主题",
			"followEdge",
			"view_object",
			friendTags,
			7*24*time.Hour,
		))
	}

	if contentReason, ok := s.friendContentReason(ctx, now, userID); ok {
		reasons = append(reasons, contentReason)
	}

	return reasons, nil
}

func (s *MongoIntersectionSource) AffinityReasons(ctx context.Context, userID, channel string) ([]app.IntersectionReasonView, error) {
	now := time.Now().UTC()
	reasons := make([]app.IntersectionReasonView, 0, 2)

	if circleIDs, err := s.social.GetUserCircleIDs(ctx, userID); err == nil && len(circleIDs) > 0 {
		candidates, err := s.candidates.GetCircleHotContent(ctx, circleIDs, 4, 7*24*time.Hour)
		if err == nil && len(candidates) > 0 {
			reasons = append(reasons, buildContentReason(
				now,
				"content",
				"circle_hot",
				"圈子热看",
				"圈子里最近更热的内容",
				"social_circle",
				"open_object",
				candidates,
				7*24*time.Hour,
				"affinity",
			))
		}
	}

	if friendContentReason, ok := s.friendContentReason(ctx, now, userID); ok {
		friendContentReason.IntersectionClass = "affinity"
		friendContentReason.DisplayText = "你关注的人最近在看这些"
		friendContentReason.Source = "social_friend"
		friendContentReason.ActionType = "open_object"
		reasons = append(reasons, friendContentReason)
	}

	return reasons, nil
}

func (s *MongoIntersectionSource) ObjectReasons(ctx context.Context, viewerID, objectID, objectType string) ([]app.IntersectionReasonView, error) {
	now := time.Now().UTC()
	dimension := objectDimension(objectType)
	objectTags, err := s.entityTags.GetEntityTags(ctx, objectID)
	if err != nil {
		objectTags = nil
	}

	reasons := make([]app.IntersectionReasonView, 0, 2)
	if len(objectTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			dimension,
			objectID+"_tags",
			objectLabel(objectType),
			objectDisplayText(objectType, objectTags),
			"tagRef",
			"view_object",
			objectTags,
			30*24*time.Hour,
		))
	}

	if relReason, ok := s.viewerRelationReason(ctx, now, viewerID, objectID, objectType); ok {
		reasons = append(reasons, relReason)
	}

	kind := objectKindForObjectType(objectType)
	for i := range reasons {
		if reasons[i].ObjectKind == "" {
			reasons[i].ObjectKind = kind
		}
	}
	return reasons, nil
}

func (s *MongoIntersectionSource) socialCircleTags(ctx context.Context, userID string) ([]string, error) {
	tags, err := s.social.GetUserCircleTags(ctx, userID)
	if err != nil || len(tags) == 0 {
		return nil, err
	}
	return topWeightKeys(tags, 3), nil
}

func (s *MongoIntersectionSource) socialFriendTags(ctx context.Context, userID string) ([]string, error) {
	tags, err := s.social.GetFriendInterestIntersection(ctx, userID)
	if err != nil || len(tags) == 0 {
		return nil, err
	}
	return topWeightKeys(tags, 3), nil
}

func (s *MongoIntersectionSource) friendContentReason(ctx context.Context, now time.Time, userID string) (app.IntersectionReasonView, bool) {
	contentIDs, err := s.social.GetFriendInteractedContent(ctx, userID, 5)
	if err != nil || len(contentIDs) == 0 {
		return app.IntersectionReasonView{}, false
	}
	candidates, err := s.candidates.GetCandidatesByIDs(ctx, contentIDs)
	if err != nil || len(candidates) == 0 {
		return app.IntersectionReasonView{}, false
	}
	return buildContentReason(
		now,
		"content",
		"friend_content",
		"好友在看",
		"你关注的人最近看过这些内容",
		"social_friend",
		"open_object",
		candidates,
		7*24*time.Hour,
		"fact",
	), true
}

func (s *MongoIntersectionSource) viewerRelationReason(ctx context.Context, now time.Time, viewerID, objectID, objectType string) (app.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil {
		return app.IntersectionReasonView{}, false
	}
	followColl := s.social.db.Collection("follow_edges")
	var follow struct {
		FollowerID string `bson:"followerId"`
		FolloweeID string `bson:"followeeId"`
	}
	viewerFollows := followColl.FindOne(ctx, bson.M{"followerId": viewerID, "followeeId": objectID}).Decode(&follow) == nil
	objectFollows := followColl.FindOne(ctx, bson.M{"followerId": objectID, "followeeId": viewerID}).Decode(&follow) == nil

	circleCount := s.sharedCircleCount(ctx, viewerID, objectID)
	if !viewerFollows && !objectFollows && circleCount == 0 {
		return app.IntersectionReasonView{}, false
	}

	points := make([]app.IntersectionPointView, 0, 2)
	if viewerFollows && objectFollows {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_mutual",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "互相关注",
			DisplayText: "你们互相关注",
			SourceRef:   "mutualFriend",
			Visibility:  "public",
			Count:       1,
		})
	} else if viewerFollows {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_follow",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "已关注",
			DisplayText: "你已关注对方",
			SourceRef:   "commonFollow",
			Visibility:  "public",
			Count:       1,
		})
	} else if objectFollows {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_followed_by",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "被关注",
			DisplayText: "对方关注了你",
			SourceRef:   "commonFollow",
			Visibility:  "public",
			Count:       1,
		})
	}
	if circleCount > 0 {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_circle",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "共同圈子",
			DisplayText: "你们在同一个圈子里",
			SourceRef:   "friendJoinedRelatedCircle",
			Visibility:  "public",
			Count:       circleCount,
		})
	}
	if len(points) == 0 {
		return app.IntersectionReasonView{}, false
	}
	relationKind := "mutual"
	if !viewerFollows && objectFollows {
		relationKind = "followed_by"
	} else if viewerFollows && !objectFollows {
		relationKind = "following"
	}
	return app.IntersectionReasonView{
		IntersectionID:     objectID + "_relationship",
		IntersectionClass:  "fact",
		Dimension:          "relationship",
		DisplayName:        objectLabel(objectType),
		AvatarURL:          "",
		Label:              "关系证据",
		DisplayText:        "你和这个对象存在真实社交关系证据",
		SharedCount:        len(points),
		Strength:           scoreFromCount(len(points), 4),
		ConfidenceLabel:    "",
		RelationKind:       relationKind,
		RelationObjectID:   objectID,
		ActionType:         relationActionType(objectType),
		ActionTargetID:     objectID,
		Source:             "followEdge",
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(7 * 24 * time.Hour).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
	}, true
}

func (s *MongoIntersectionSource) sharedCircleCount(ctx context.Context, viewerID, objectID string) int {
	if s.social == nil || s.social.db == nil {
		return 0
	}
	coll := s.social.db.Collection("circle_members")
	viewerCircles := map[string]struct{}{}
	cur, err := coll.Find(ctx, bson.M{"userId": viewerID})
	if err == nil {
		for cur.Next(ctx) {
			var doc struct {
				CircleID string `bson:"circleId"`
			}
			if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.CircleID) != "" {
				viewerCircles[doc.CircleID] = struct{}{}
			}
		}
		_ = cur.Close(ctx)
	}
	if len(viewerCircles) == 0 {
		return 0
	}
	count := 0
	cur2, err := coll.Find(ctx, bson.M{"userId": objectID})
	if err != nil {
		return 0
	}
	defer cur2.Close(ctx)
	for cur2.Next(ctx) {
		var doc struct {
			CircleID string `bson:"circleId"`
		}
		if err := cur2.Decode(&doc); err == nil {
			if _, ok := viewerCircles[doc.CircleID]; ok {
				count++
			}
		}
	}
	return count
}

func buildTagReason(
	now time.Time,
	dimension string,
	intersectionID string,
	label string,
	displayText string,
	source string,
	actionType string,
	values []string,
	ttl time.Duration,
) app.IntersectionReasonView {
	points := make([]app.IntersectionPointView, 0, len(values))
	for i, value := range values {
		points = append(points, app.IntersectionPointView{
			PointID:     intersectionID + "_p_" + strconv.Itoa(i),
			PointClass:  "fact",
			Dimension:   dimension,
			Label:       value,
			DisplayText: value,
			SourceRef:   source,
			Visibility:  "public",
			Count:       1,
			SampleText:  value,
		})
	}
	return app.IntersectionReasonView{
		IntersectionID:     intersectionID,
		IntersectionClass:  "fact",
		Dimension:          dimension,
		Label:              label,
		DisplayText:        displayText,
		SharedCount:        len(points),
		Strength:           scoreFromCount(len(points), 6),
		RelationKind:       "mutual",
		RelationObjectID:   intersectionID,
		ActionType:         actionType,
		ActionTargetID:     intersectionID,
		Source:             source,
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(ttl).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
	}
}

func buildContentReason(
	now time.Time,
	dimension string,
	intersectionID string,
	label string,
	displayText string,
	source string,
	actionType string,
	candidates []rtrec.ContentCandidate,
	ttl time.Duration,
	class string,
) app.IntersectionReasonView {
	limit := len(candidates)
	if limit > 3 {
		limit = 3
	}
	points := make([]app.IntersectionPointView, 0, limit)
	for i := 0; i < limit; i++ {
		c := candidates[i]
		points = append(points, app.IntersectionPointView{
			PointID:     c.ContentID,
			PointClass:  "fact",
			Dimension:   dimension,
			Label:       c.Title,
			DisplayText: c.Title,
			SourceRef:   source,
			Visibility:  "public",
			Count:       1,
			SampleText:  c.Title,
		})
	}
	return app.IntersectionReasonView{
		IntersectionID:     intersectionID,
		IntersectionClass:  class,
		Dimension:          dimension,
		Label:              label,
		DisplayText:        displayText,
		SharedCount:        len(points),
		Strength:           scoreFromCount(len(points), 4),
		RelationKind:       "mutual",
		RelationObjectID:   intersectionID,
		ActionType:         actionType,
		ActionTargetID:     firstCandidateID(candidates),
		Source:             source,
		FreshAt:            now.Format(time.RFC3339),
		ExpiresAt:          now.Add(ttl).Format(time.RFC3339),
		IntersectionPoints: points,
		FactPointCount:     len(points),
		TotalPointCount:    len(points),
	}
}

func topWeightKeys(values map[string]float64, limit int) []string {
	type kv struct {
		key   string
		value float64
	}
	items := make([]kv, 0, len(values))
	for key, value := range values {
		items = append(items, kv{key: key, value: value})
	}
	sort.SliceStable(items, func(i, j int) bool {
		if items[i].value != items[j].value {
			return items[i].value > items[j].value
		}
		return items[i].key < items[j].key
	})
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	out := make([]string, 0, limit)
	for i := 0; i < limit; i++ {
		out = append(out, items[i].key)
	}
	return out
}

func firstCandidateID(candidates []rtrec.ContentCandidate) string {
	if len(candidates) == 0 {
		return ""
	}
	return candidates[0].ContentID
}

func scoreFromCount(count, saturate int) float64 {
	if saturate <= 0 {
		saturate = 1
	}
	if count <= 0 {
		return 0.5
	}
	v := 0.5 + 0.5*float64(count)/float64(saturate)
	if v > 1.0 {
		return 1.0
	}
	return v
}

func objectDimension(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "university":
		return "identity"
	case "travel_photo", "sight":
		return "location"
	default:
		return "interest"
	}
}

func objectLabel(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "university":
		return "同校"
	case "travel_photo", "sight":
		return "同游"
	default:
		return "同好"
	}
}

func objectDisplayText(objectType string, tags []string) string {
	switch strings.TrimSpace(objectType) {
	case "university":
		return "你们在同一个校园或组织里有交集"
	case "travel_photo", "sight":
		return "你们都关注过这些地点"
	default:
		return "你们都关注这些主题"
	}
}

func relationActionType(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "university", "travel_photo", "sight":
		return "view_object"
	default:
		return "open_profile"
	}
}

// objectKindForObjectType 将开放 objectType 收口到闭集 objectKind（人/圈/校/地/企角标真相源）。
func objectKindForObjectType(objectType string) string {
	switch strings.TrimSpace(objectType) {
	case "user", "person":
		return "person"
	case "circle":
		return "circle"
	case "university", "school":
		return "school"
	case "sight", "travel_photo", "place", "entity", "homepage":
		return "place"
	case "brand", "enterprise", "company":
		return "enterprise"
	default:
		return ""
	}
}

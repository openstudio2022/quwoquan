package recommendation

import (
	"context"
	"sort"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

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
			"sharedTagSample",
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
			"followeeDiscussedThis",
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
				"sharedCircle",
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

	reasons := make([]app.IntersectionReasonView, 0, 3)
	if len(objectTags) > 0 {
		reasons = append(reasons, buildTagReason(
			now,
			dimension,
			objectID+"_tags",
			objectLabel(objectType),
			objectDisplayText(objectType, objectTags),
			"tagRef",
			"sharedTagSample",
			"view_object",
			objectTags,
			30*24*time.Hour,
		))
	}

	if relReason, ok := s.viewerRelationReason(ctx, now, viewerID, objectID, objectType); ok {
		reasons = append(reasons, relReason)
	}

	if objectKindForObjectType(objectType) != "person" {
		if visitReason, ok := s.followeeVisitedReason(ctx, now, viewerID, objectID, objectType); ok {
			reasons = append(reasons, visitReason)
		}
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
		"关注的人在看",
		"你关注的人最近看过这些内容",
		"social_friend",
		"followeeViewing",
		"open_object",
		candidates,
		7*24*time.Hour,
		"fact",
	), true
}

// 真实数据源查询上限：限制单次交集计算扫描的边数，保证对象页拉取 P99 可控。
const (
	maxFolloweeScan      = 200
	maxBehaviorScan      = 300
	maxIntersectionPoint = 3
)

// followeeSet 读取 follow_edges 中 userID 关注的人（上限 maxFolloweeScan）。
func (s *MongoIntersectionSource) followeeSet(ctx context.Context, userID string) map[string]struct{} {
	out := map[string]struct{}{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("follow_edges").Find(ctx,
		bson.M{"followerId": userID}, mongoFindLimit(maxFolloweeScan))
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			FolloweeID string `bson:"followeeId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.FolloweeID) != "" {
			out[doc.FolloweeID] = struct{}{}
		}
	}
	return out
}

// behaviorRefs 读取 rm_behavior_events 中 userID 指定 action 的目标引用集合。
// useEntityRefs=true 时取 entityRefs（实体到访），否则取 contentId（内容互动）。
func (s *MongoIntersectionSource) behaviorRefs(ctx context.Context, userID, action string, useEntityRefs bool) map[string]struct{} {
	out := map[string]struct{}{}
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return out
	}
	cur, err := s.social.db.Collection("rm_behavior_events").Find(ctx,
		bson.M{"userId": userID, "action": action}, mongoFindLimit(maxBehaviorScan))
	if err != nil {
		return out
	}
	defer cur.Close(ctx)
	for cur.Next(ctx) {
		var doc struct {
			ContentID  string   `bson:"contentId"`
			EntityRefs []string `bson:"entityRefs"`
		}
		if err := cur.Decode(&doc); err != nil {
			continue
		}
		if useEntityRefs {
			for _, ref := range doc.EntityRefs {
				if strings.TrimSpace(ref) != "" {
					out[ref] = struct{}{}
				}
			}
		} else if strings.TrimSpace(doc.ContentID) != "" {
			out[doc.ContentID] = struct{}{}
		}
	}
	return out
}

// intersectKeys 返回两集合交集（排除 exclude 中的 key），结果排序保证幂等。
func intersectKeys(a, b map[string]struct{}, exclude ...string) []string {
	skip := map[string]struct{}{}
	for _, e := range exclude {
		skip[e] = struct{}{}
	}
	out := make([]string, 0)
	for k := range a {
		if _, ok := b[k]; !ok {
			continue
		}
		if _, ok := skip[k]; ok {
			continue
		}
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

// viewerRelationReason 产出 viewer↔object（人）之间的事实交集证据组：
// sharedFollowees（共同关注的人）/ sharedCircle（共同圈子）/
// coCommented（共同讨论）/ coVisitedEntity（共同到访实体）。
// 关注状态本身（互关/单向）不再作为交集点，由 relationKind 承载。
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

	points := make([]app.IntersectionPointView, 0, 4)

	// sharedFollowees：双方共同关注的第三方集合（排除彼此）。
	sharedFollowees := intersectKeys(
		s.followeeSet(ctx, viewerID), s.followeeSet(ctx, objectID), viewerID, objectID)
	if n := len(sharedFollowees); n > 0 {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_shared_followees",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "共同关注的人",
			DisplayText: strconv.Itoa(n) + "位共同关注的人",
			SourceRef:   "sharedFollowees",
			Visibility:  "public",
			Count:       n,
			SampleText:  strings.Join(headKeys(sharedFollowees, maxIntersectionPoint), "、"),
		})
	}

	// sharedCircle：共同圈子。
	if circleCount := s.sharedCircleCount(ctx, viewerID, objectID); circleCount > 0 {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_circle",
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "共同圈子",
			DisplayText: strconv.Itoa(circleCount) + "个共同圈子",
			SourceRef:   "sharedCircle",
			Visibility:  "public",
			Count:       circleCount,
		})
	}

	// coCommented：双方都评论过的内容。
	coCommented := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "comment", false),
		s.behaviorRefs(ctx, objectID, "comment", false))
	if n := len(coCommented); n > 0 {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_co_commented",
			PointClass:  "fact",
			Dimension:   "content",
			Label:       "共同讨论",
			DisplayText: "讨论过" + strconv.Itoa(n) + "篇相同内容",
			SourceRef:   "coCommented",
			Visibility:  "public",
			Count:       n,
			SampleText:  strings.Join(headKeys(coCommented, maxIntersectionPoint), "、"),
		})
	}

	// coVisitedEntity：双方都到访过的实体（实体页浏览行为的 entityRefs 交集）。
	coVisited := intersectKeys(
		s.behaviorRefs(ctx, viewerID, "entity_page_view", true),
		s.behaviorRefs(ctx, objectID, "entity_page_view", true))
	if n := len(coVisited); n > 0 {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_co_visited",
			PointClass:  "fact",
			Dimension:   "location",
			Label:       "共同去过",
			DisplayText: "都去过" + strconv.Itoa(n) + "个相同的地方",
			SourceRef:   "coVisitedEntity",
			Visibility:  "public",
			Count:       n,
			SampleText:  strings.Join(headKeys(coVisited, maxIntersectionPoint), "、"),
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
	} else if !viewerFollows && !objectFollows {
		relationKind = "none"
	}
	primary := points[0]
	// T3 空窗治理：人级 reason 回填对方真实展示资料，避免 spotlight 空头像。
	displayName, avatarURL := s.userDisplayProfile(ctx, objectID)
	if displayName == "" {
		displayName = objectLabel(objectType)
	}
	return app.IntersectionReasonView{
		IntersectionID:     objectID + "_relationship",
		IntersectionClass:  "fact",
		Dimension:          "relationship",
		DisplayName:        displayName,
		AvatarURL:          avatarURL,
		Label:              primary.Label,
		DisplayText:        primary.DisplayText,
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

// followeeVisitedReason 桥接型交集：viewer 关注的人里有谁到访过该对象（实体/地点页）。
func (s *MongoIntersectionSource) followeeVisitedReason(ctx context.Context, now time.Time, viewerID, objectID, objectType string) (app.IntersectionReasonView, bool) {
	if s.social == nil || s.social.db == nil || strings.TrimSpace(viewerID) == "" {
		return app.IntersectionReasonView{}, false
	}
	followees := s.followeeSet(ctx, viewerID)
	if len(followees) == 0 {
		return app.IntersectionReasonView{}, false
	}
	followeeIDs := make([]string, 0, len(followees))
	for id := range followees {
		followeeIDs = append(followeeIDs, id)
	}
	cur, err := s.social.db.Collection("rm_behavior_events").Find(ctx, bson.M{
		"userId":     bson.M{"$in": followeeIDs},
		"action":     "entity_page_view",
		"entityRefs": objectID,
	}, mongoFindLimit(maxBehaviorScan))
	if err != nil {
		return app.IntersectionReasonView{}, false
	}
	defer cur.Close(ctx)
	visitors := map[string]struct{}{}
	for cur.Next(ctx) {
		var doc struct {
			UserID string `bson:"userId"`
		}
		if err := cur.Decode(&doc); err == nil && strings.TrimSpace(doc.UserID) != "" {
			visitors[doc.UserID] = struct{}{}
		}
	}
	if len(visitors) == 0 {
		return app.IntersectionReasonView{}, false
	}
	visitorIDs := make([]string, 0, len(visitors))
	for id := range visitors {
		visitorIDs = append(visitorIDs, id)
	}
	sort.Strings(visitorIDs)
	n := len(visitorIDs)
	displayText := strconv.Itoa(n) + "位你关注的人来过这里"
	points := make([]app.IntersectionPointView, 0, maxIntersectionPoint)
	for i, id := range headKeys(visitorIDs, maxIntersectionPoint) {
		points = append(points, app.IntersectionPointView{
			PointID:     objectID + "_followee_visited_" + strconv.Itoa(i),
			PointClass:  "fact",
			Dimension:   "relationship",
			Label:       "你关注的人来过",
			DisplayText: "你关注的人来过这里",
			SourceRef:   "followeeVisited",
			Visibility:  "public",
			Count:       1,
			SampleText:  id,
		})
	}
	return app.IntersectionReasonView{
		IntersectionID:     objectID + "_followee_visited",
		IntersectionClass:  "fact",
		Dimension:          "relationship",
		DisplayName:        objectLabel(objectType),
		Label:              "你关注的人来过",
		DisplayText:        displayText,
		SharedCount:        n,
		Strength:           scoreFromCount(n, 4),
		RelationKind:       "bridge",
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

// userDisplayProfile 从 posts 集合的作者快照回填用户展示资料（T3 空窗治理：
// content-service 域内唯一的用户展示读模型；无发布内容的用户回退空，由
// 候选窗完备性过滤兜底，不下发空头像的人级 reason 进 spotlight）。
func (s *MongoIntersectionSource) userDisplayProfile(ctx context.Context, userID string) (displayName, avatarURL string) {
	if s.social == nil || s.social.db == nil || strings.TrimSpace(userID) == "" {
		return "", ""
	}
	var doc struct {
		AuthorDisplayNameSnapshot string `bson:"authorDisplayNameSnapshot"`
		AuthorAvatarUrlSnapshot   string `bson:"authorAvatarUrlSnapshot"`
	}
	err := s.social.db.Collection("posts").FindOne(ctx,
		bson.M{"authorId": userID, "status": "published"},
		mongoopts.FindOne().SetSort(bson.M{"updatedAt": -1}),
	).Decode(&doc)
	if err != nil {
		return "", ""
	}
	return strings.TrimSpace(doc.AuthorDisplayNameSnapshot), strings.TrimSpace(doc.AuthorAvatarUrlSnapshot)
}

// headKeys 取有序切片前 limit 个。
func headKeys(keys []string, limit int) []string {
	if limit <= 0 || limit >= len(keys) {
		return keys
	}
	return keys[:limit]
}

func mongoFindLimit(limit int64) *mongoopts.FindOptionsBuilder {
	return mongoopts.Find().SetLimit(limit)
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
	pointKind string,
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
			SourceRef:   pointKind,
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
	pointKind string,
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
			SourceRef:   pointKind,
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

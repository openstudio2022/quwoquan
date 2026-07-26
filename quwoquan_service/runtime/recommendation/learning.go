package recommendation

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strconv"
	"strings"
	"time"

	learning "quwoquan_service/runtime/learning"
)

const scoreKeyPrefix = "rec:imp_score:"
const scoreTTL = 2 * time.Hour

// FeedbackRecorder records recommendation outcomes for offline learning.
// It also caches impression scores so that RecordEngagement can recover
// the original recommendation score for a content item.
type FeedbackRecorder struct {
	recorder   learning.Recorder
	scoreCache RedisClient
}

// trainingFeatureSnapshot 是一次真正下发时的不可变训练输入。
// 它只保留当前模型向量实际消费的稀疏字段，既保证与在线评分同源，也避免把整张
// 用户特征宽表复制进每条曝光事实。
type trainingFeatureSnapshot struct {
	userFeatures map[string]any
	itemFeatures map[string]any
	capturedAt   time.Time
}

func newTrainingFeatureSnapshot(
	user *UserFeatureVector,
	candidate CandidateInput,
	capturedAt time.Time,
) *trainingFeatureSnapshot {
	if capturedAt.IsZero() {
		capturedAt = time.Now().UTC()
	}
	return &trainingFeatureSnapshot{
		userFeatures: trainingUserFeatures(user, candidate),
		itemFeatures: trainingItemFeatures(candidate),
		capturedAt:   capturedAt.UTC(),
	}
}

func trainingUserFeatures(user *UserFeatureVector, candidate CandidateInput) map[string]any {
	if user == nil {
		return map[string]any{}
	}
	return map[string]any{
		"tagAffinities":             selectFloatFeatures(user.TagAffinities, candidate.Tags),
		"authorAffinities":          selectFloatFeatures(user.AuthorAffinities, []string{candidate.AuthorID}),
		"engagementRate":            user.EngagementRate,
		"totalLikes":                user.TotalLikes,
		"totalShares":               user.TotalShares,
		"totalEvents":               user.TotalEvents,
		"topicAffinities":           selectFloatFeatures(user.TopicAffinities, candidate.Tags),
		"audienceAffinities":        selectFloatFeatures(user.AudienceAffinities, candidate.Tags),
		"formatAffinities":          selectFloatFeatures(user.FormatAffinities, candidate.Tags),
		"entityAffinities":          selectFloatFeatures(user.EntityAffinities, candidate.Tags),
		"entityInstanceAffinities":  selectFloatFeatures(user.EntityInstanceAffinities, candidate.EntityRefs),
		"avgEngagementDepth":        user.AvgEngagementDepth,
		"depthDistribution":         cloneIntFeatures(user.DepthDistribution),
		"circleTagAffinities":       selectFloatFeatures(user.CircleTagAffinities, candidate.Tags),
		"socialInterestScore":       user.SocialInterestScore,
		"typeENER":                  selectFloatFeatures(user.TypeENER, []string{candidate.ContentType}),
		"sharedFolloweesCount":      user.SharedFolloweesCount,
		"sharedCircleCount":         user.SharedCircleCount,
		"coCommentedCount":          user.CoCommentedCount,
		"coVisitedEntityCount":      user.CoVisitedEntityCount,
		"followeeInObjectActive":    user.FolloweeInObjectActive,
		"followeeViewingActive":     user.FolloweeViewingActive,
		"affinityIntersectionScore": user.AffinityIntersectionScore,
		"intersectionSourceRefTop":  user.IntersectionSourceRefTop,
	}
}

func trainingItemFeatures(candidate CandidateInput) map[string]any {
	return map[string]any{
		"contentId":                   candidate.ContentID,
		"contentType":                 candidate.ContentType,
		"authorId":                    candidate.AuthorID,
		"tagRefs":                     append([]string(nil), candidate.Tags...),
		"entityRefs":                  append([]string(nil), candidate.EntityRefs...),
		"ageHours":                    candidate.AgeHours,
		"publishHour":                 candidate.PublishHour,
		"viewCount":                   candidate.ViewCount,
		"likeCount":                   candidate.LikeCount,
		"commentCount":                candidate.CommentCount,
		"shareCount":                  candidate.ShareCount,
		"tagCount":                    len(candidate.Tags),
		"recallPath":                  candidate.RecallPath,
		"qualityScore":                candidate.QualityScore,
		"contentVertical":             candidate.ContentVertical,
		"supplySource":                candidate.SupplySource,
		"intersectionFactStrength":    candidate.IntersectionFactStrength,
		"intersectionFreshness":       candidate.IntersectionFreshness,
		"affinityIntersectionScore":   candidate.AffinityIntersectionScore,
		"intersectionSourceRefTop":    candidate.IntersectionSourceRefTop,
		"intersectionConfidenceLabel": candidate.IntersectionConfidenceLabel,
		"intersectionClass":           candidate.IntersectionClass,
	}
}

func selectFloatFeatures(source map[string]float64, keys []string) map[string]float64 {
	selected := make(map[string]float64, len(keys))
	for _, key := range keys {
		if value, ok := source[key]; ok {
			selected[key] = value
		}
	}
	return selected
}

func cloneIntFeatures(source map[string]int) map[string]int {
	cloned := make(map[string]int, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func NewFeedbackRecorder(recorder learning.Recorder, opts ...FeedbackRecorderOption) *FeedbackRecorder {
	f := &FeedbackRecorder{recorder: recorder}
	for _, opt := range opts {
		opt(f)
	}
	return f
}

type FeedbackRecorderOption func(*FeedbackRecorder)

func WithScoreCache(rc RedisClient) FeedbackRecorderOption {
	return func(f *FeedbackRecorder) { f.scoreCache = rc }
}

func (f *FeedbackRecorder) cacheImpressionScore(ctx context.Context, userID, contentID string, score float64) {
	if f.scoreCache == nil {
		return
	}
	key := scoreKeyPrefix + userID + ":" + contentID
	_ = f.scoreCache.Set(ctx, key, strconv.FormatFloat(score, 'f', 6, 64), scoreTTL)
}

func (f *FeedbackRecorder) lookupImpressionScore(ctx context.Context, userID, contentID string) float64 {
	if f.scoreCache == nil {
		return 0
	}
	key := scoreKeyPrefix + userID + ":" + contentID
	val, err := f.scoreCache.Get(ctx, key)
	if err != nil || val == "" {
		return 0
	}
	score, _ := strconv.ParseFloat(val, 64)
	return score
}

// deterministicEventID 从稳定归因输入派生 learning 事件 id（作为 Mongo _id 承载
// dedupe，见 recommendation/recommendation/recommendation_model_release/storage.yaml）。禁止时间戳参与派生。
func deterministicEventID(prefix string, parts ...string) string {
	digest := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	return prefix + "_" + hex.EncodeToString(digest[:16])
}

// recImpressionContext builds a typed context map for rec_impression events.
func recImpressionContext(
	score float64,
	authorID string,
	tags []string,
	rank int,
	feedRequestID, modelBucket, modelVersion, modelReleaseID string,
) map[string]any {
	return map[string]any{
		"score":          score,
		"authorId":       authorID,
		"tagRefs":        tags,
		"rank":           rank,
		"feedRequestId":  feedRequestID,
		"modelBucket":    modelBucket,
		"modelVersion":   modelVersion,
		"modelReleaseId": modelReleaseID,
	}
}

// recEngagementContext builds a typed context map for rec_engagement events.
func recEngagementContext(duration float64, recScore float64, tags []string, feedRequestID string, referralSource string, contentType string, authorID string) map[string]any {
	return map[string]any{
		"duration":       duration,
		"recScore":       recScore,
		"tagRefs":        tags,
		"feedRequestId":  feedRequestID,
		"referralSource": referralSource,
		"contentType":    contentType,
		"authorId":       authorID,
	}
}

// ImpressionAttribution 是一次 feed 下发的曝光归因（fact 契约字段来源）。
// FeedRequestID 是曝光批次的稳定归因键；ModelBucket/ModelVersion 是本次
// 命中的评分轨道（rule 分桶时 ModelVersion 为空）。PersonaID 是服务端已验证的
// 人格身份，必须随曝光事实保留，不能由客户端行为 payload 补写。
type ImpressionAttribution struct {
	FeedRequestID  string
	PersonaID      string
	ModelBucket    string
	ModelVersion   string
	ModelReleaseID string
}

type impressionScoreCacheEntry struct {
	contentID string
	score     float64
}

// RecordImpression records that a feed item was shown to the user.
// EventID 从 feedRequestId+targetId 确定性派生：同一 feed 批次同一内容重放
// 不产生第二条曝光事实（Mongo _id dedupe）。
// 同时按内容缓存推荐分数，供后续 engagement 恢复原始分数。
func (f *FeedbackRecorder) RecordImpression(
	ctx context.Context,
	userID, sessionID string,
	attribution ImpressionAttribution,
	items []FeedItem,
) error {
	if f.recorder == nil {
		return nil
	}
	batchKey := strings.TrimSpace(attribution.FeedRequestID)
	if batchKey == "" {
		// RecommendationExposureFact 以 requestId+targetId 作为唯一训练归因键。
		// 不能用 user/session 临时替代，否则事实虽落库却无法与反馈可靠关联，
		// SampleJoiner 只能静默丢弃并掩盖数据质量问题。
		return fmt.Errorf("record recommendation impression: missing feed request id")
	}
	attribution.FeedRequestID = batchKey
	for _, item := range items {
		if err := validateImpressionTrainingSnapshot(item); err != nil {
			return err
		}
	}
	scoreEntries := make([]impressionScoreCacheEntry, 0, len(items))
	for itemIndex, item := range items {
		occurredAt := time.Now().UTC()
		rank := item.rank
		if rank <= 0 {
			// 仅供直接调用 RecordImpression 的测试/离线回放；线上 Engine
			// 始终提供全局重排序位，不能退化成端侧 position。
			rank = itemIndex + 1
		}
		contextMap := recImpressionContext(
			item.Score,
			item.AuthorID,
			item.Tags,
			rank,
			attribution.FeedRequestID,
			attribution.ModelBucket,
			attribution.ModelVersion,
			attribution.ModelReleaseID,
		)
		snapshot := item.trainingFeatures
		contextMap["featureSnapshotAt"] = snapshot.capturedAt.Format(time.RFC3339Nano)
		contextMap["userFeatureSnapshot"] = snapshot.userFeatures
		contextMap["itemFeatureSnapshot"] = snapshot.itemFeatures
		if err := f.recorder.RecordEvent(ctx, learning.Event{
			EventID:   deterministicEventID("rec_imp", batchKey, item.ContentID),
			EventType: "rec_impression",
			Scenario:  "content_feed",
			// 必须保留亚秒精度。FeatureSnapshotAt 使用 RFC3339Nano；若这里截断到秒，
			// 同一秒内稍早生成的曝光会看似早于快照并被 PIT 门禁误判为未来特征。
			OccurredAt: occurredAt.Format(time.RFC3339Nano),
			UserID:     userID,
			PersonaID:  attribution.PersonaID,
			TargetID:   item.ContentID,
			Labels: map[string]string{
				"sessionId":   sessionID,
				"contentType": item.ContentType,
				"recallPath":  item.RecallPath,
			},
			Context: contextMap,
		}); err != nil {
			return fmt.Errorf("record recommendation impression %q: %w", item.ContentID, err)
		}
		scoreEntries = append(scoreEntries, impressionScoreCacheEntry{
			contentID: item.ContentID,
			score:     item.Score,
		})
	}
	if f.scoreCache != nil && len(scoreEntries) > 0 {
		// 训练事实先同步进入 BufferedRecorder；分数缓存只是后续 engagement
		// 补分的可重建加速层，异步写入避免 N 个 Redis RTT 拉长 feed P95。
		go func() {
			cacheCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
			defer cancel()
			for _, entry := range scoreEntries {
				f.cacheImpressionScore(
					cacheCtx,
					userID,
					entry.contentID,
					entry.score,
				)
			}
		}()
	}
	return nil
}

func validateImpressionTrainingSnapshot(item FeedItem) error {
	snapshot := item.trainingFeatures
	if snapshot == nil {
		return fmt.Errorf(
			"record recommendation impression %q: missing immutable online feature snapshot",
			item.ContentID,
		)
	}
	if snapshot.capturedAt.IsZero() {
		return fmt.Errorf(
			"record recommendation impression %q: missing feature snapshot timestamp",
			item.ContentID,
		)
	}
	if snapshot.userFeatures == nil || snapshot.itemFeatures == nil {
		return fmt.Errorf(
			"record recommendation impression %q: incomplete immutable feature snapshot",
			item.ContentID,
		)
	}
	return nil
}

// RecordEngagement records a user engagement event on a recommended item.
// If recScore is 0, it attempts to recover the original score from the impression cache.
func (f *FeedbackRecorder) RecordEngagement(ctx context.Context, signal BehaviorSignal, recScore float64) error {
	if f.recorder == nil {
		return nil
	}
	signal.FeedRequestID = strings.TrimSpace(signal.FeedRequestID)
	if signal.FeedRequestID == "" {
		// RecommendationFeedbackFact.requestId 是必填归因键。客户端事件或
		// 服务端权威事实若没有对应的最终下发 requestId，仍可进入 HotPath 与
		// 长期特征投影，但绝不能伪造一条不可训练的 learning event。
		return fmt.Errorf(
			"record recommendation engagement %q: missing feed request id",
			signal.ContentID,
		)
	}
	if recScore == 0 {
		recScore = f.lookupImpressionScore(ctx, signal.UserID, signal.ContentID)
	}
	contextMap := recEngagementContext(signal.Duration, recScore, signal.Tags, signal.FeedRequestID, signal.ReferralSource, signal.ContentType, signal.AuthorID)
	contextMap["channelId"] = signal.ChannelID
	contextMap["rankingVersion"] = signal.RankingVersion
	contextMap["reasonVersion"] = signal.ReasonVersion
	contextMap["recallPath"] = signal.RecallPath
	contextMap["contentVertical"] = signal.ContentVertical
	contextMap["supplySource"] = signal.SupplySource
	contextMap["intersectionSourceRef"] = signal.IntersectionSourceRef
	contextMap["intersectionClass"] = signal.IntersectionClass
	// 反馈事实的 dedupe 身份是 requestId+targetId+action；该键与
	// RecommendationFeedbackFact 和 SampleJoiner 的关联契约完全一致。
	engagementKey := []string{signal.FeedRequestID, signal.ContentID, signal.Action}
	return f.recorder.RecordEvent(ctx, learning.Event{
		EventID:    deterministicEventID("rec_eng", engagementKey...),
		EventType:  "rec_engagement",
		Scenario:   "content_feed",
		OccurredAt: time.Now().UTC().Format(time.RFC3339Nano),
		UserID:     signal.UserID,
		PersonaID:  signal.PersonaID,
		TargetID:   signal.ContentID,
		Labels: map[string]string{
			"sessionId":     signal.EffectiveSessionID(),
			"feedSessionId": signal.FeedSessionID,
			"action":        signal.Action,
			"channelId":     signal.ChannelID,
			"recallPath":    signal.RecallPath,
		},
		Context: contextMap,
	})
}

// RecordScorecard records an aggregate scoring metric for model evaluation.
func (f *FeedbackRecorder) RecordScorecard(ctx context.Context, userID, bucket string, dwellMs float64, interacted bool) error {
	if f.recorder == nil {
		return nil
	}
	score := dwellMs
	if interacted {
		score += 1000
	}
	comment := fmt.Sprintf("bucket=%s dwell=%.0fms interacted=%v", bucket, dwellMs, interacted)
	return f.recorder.RecordScorecard(ctx, learning.Scorecard{
		ScorecardID: fmt.Sprintf("rec_sc_%s_%d", userID, time.Now().UnixNano()),
		RunID:       bucket,
		Score:       score,
		Comment:     comment,
		Version:     "v1",
	})
}

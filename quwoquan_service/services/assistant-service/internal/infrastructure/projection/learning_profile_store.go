package projection

import (
	"context"
	"crypto/sha1"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
)

type LearningProfileStore struct {
	coll *mongo.Collection
}

func NewLearningProfileStore(db *mongo.Database) *LearningProfileStore {
	return &LearningProfileStore{coll: db.Collection("rm_assistant_learning_profile")}
}

func (s *LearningProfileStore) EnsureIndexes(ctx context.Context) error {
	models := []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}}, Options: options.Index().SetName("idx_alp_user").SetUnique(true)},
		{Keys: bson.D{{Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_alp_updated")},
		{Keys: bson.D{{Key: "lastFeedbackAt", Value: -1}}, Options: options.Index().SetName("idx_alp_last_feedback").SetSparse(true)},
	}
	_, err := s.coll.Indexes().CreateMany(ctx, models)
	return err
}

func (s *LearningProfileStore) ProjectInteractionEvent(ctx context.Context, event assistant.InteractionEvent, priority string) error {
	if strings.TrimSpace(event.UserID) == "" {
		return nil
	}
	filter := bson.M{"userId": event.UserID}
	set := bson.M{
		"userId":               event.UserID,
		"lastRunId":            event.RunID,
		"lastEventId":          event.EventID,
		"lastPageType":         event.PageType,
		"lastFeedbackType":     event.FeedbackType,
		"lastFeedbackText":     strings.TrimSpace(firstNonEmptyLocal(event.FeedbackText, event.CorrectionText)),
		"lastFeedbackScore":    event.FeedbackScore,
		"lastFeedbackAt":       event.CreatedAt,
		"lastQueryTextDigest":  digestTextLocal(event.QueryText),
		"lastAnswerTextDigest": digestTextLocal(event.AnswerText),
		"updatedAt":            event.CreatedAt,
	}
	inc := bson.M{}
	if strings.TrimSpace(event.FeedbackType) != "" || event.FeedbackScore != 0 || strings.TrimSpace(event.FeedbackText) != "" {
		inc["totalFeedbackCount"] = 1
	}
	switch strings.TrimSpace(event.FeedbackType) {
	case "thumbs_up":
		inc["positiveFeedbackCount"] = 1
	case "thumbs_down":
		inc["negativeFeedbackCount"] = 1
	case "text":
		inc["textFeedbackCount"] = 1
	}
	switch strings.TrimSpace(priority) {
	case "high":
		inc["highPriorityCount"] = 1
	case "medium":
		inc["mediumPriorityCount"] = 1
	}
	for _, reason := range sanitizeReasonsLocal(event.ExplicitReasonCodes) {
		inc["reasonCodeCounts."+reason] = 1
	}
	update := bson.M{"$set": set}
	if len(inc) > 0 {
		update["$inc"] = inc
	}
	_, err := s.coll.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return rterr.NewUnavailable(rterr.ModuleAssistant, "学习画像投影失败", err.Error())
	}
	return nil
}

func (s *LearningProfileStore) ProjectScorecard(ctx context.Context, score assistant.Scorecard, priority string) error {
	if strings.TrimSpace(score.UserID) == "" || strings.TrimSpace(score.MetricID) == "" {
		return nil
	}
	filter := bson.M{"userId": score.UserID}
	set := bson.M{
		"userId":          score.UserID,
		"lastRunId":       score.RunID,
		"lastMetricId":    score.MetricID,
		"lastMetricScore": score.ScoreValue,
		"updatedAt":       score.CreatedAt,
	}
	inc := bson.M{
		"metricSampleCounts." + score.MetricID: 1,
		"metricScoreSums." + score.MetricID:    score.ScoreValue,
	}
	if strings.TrimSpace(priority) == "high" {
		inc["highPriorityCount"] = 1
	} else if strings.TrimSpace(priority) == "medium" {
		inc["mediumPriorityCount"] = 1
	}
	update := bson.M{
		"$set": set,
		"$inc": inc,
	}
	update["$set"].(bson.M)["latestMetricScores."+score.MetricID] = score.ScoreValue
	_, err := s.coll.UpdateOne(ctx, filter, update, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return rterr.NewUnavailable(rterr.ModuleAssistant, "评分画像投影失败", err.Error())
	}
	return nil
}

func (s *LearningProfileStore) GetLearningProfile(ctx context.Context, userID string) (*assistant.AssistantLearningProfile, error) {
	if strings.TrimSpace(userID) == "" {
		return nil, nil
	}
	var out assistant.AssistantLearningProfile
	err := s.coll.FindOne(ctx, bson.M{"userId": userID}).Decode(&out)
	if err == mongo.ErrNoDocuments {
		return nil, nil
	}
	if err != nil {
		return nil, rterr.NewUnavailable(rterr.ModuleAssistant, "读取学习画像失败", err.Error())
	}
	return &out, nil
}

func (s *LearningProfileStore) BuildMemoryItems(ctx context.Context, userID string, limit int) ([]assistant.AssistantUserMemoryView, error) {
	profile, err := s.GetLearningProfile(ctx, userID)
	if err != nil || profile == nil {
		return nil, err
	}
	return buildMemoryItemsFromProfile(profile, limit), nil
}

func (s *LearningProfileStore) BuildTaskItems(ctx context.Context, userID string, now time.Time) ([]assistant.AssistantUserTaskView, error) {
	profile, err := s.GetLearningProfile(ctx, userID)
	if err != nil || profile == nil {
		return nil, err
	}
	return buildTaskItemsFromProfile(profile, now), nil
}

func topLatestMetricLocal(scores map[string]float64) (string, float64) {
	keys := make([]string, 0, len(scores))
	for key := range scores {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	if len(keys) == 0 {
		return "", 0
	}
	key := keys[0]
	return key, scores[key]
}

type MemoryLearningProfileStore struct {
	mu       sync.Mutex
	profiles map[string]assistant.AssistantLearningProfile
}

func NewMemoryLearningProfileStore() *MemoryLearningProfileStore {
	return &MemoryLearningProfileStore{profiles: map[string]assistant.AssistantLearningProfile{}}
}

func (s *MemoryLearningProfileStore) ProjectInteractionEvent(_ context.Context, event assistant.InteractionEvent, priority string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if strings.TrimSpace(event.UserID) == "" {
		return nil
	}
	profile := s.profiles[event.UserID]
	profile.UserID = event.UserID
	profile.LastRunID = event.RunID
	profile.LastEventID = event.EventID
	profile.LastPageType = event.PageType
	profile.LastFeedbackType = event.FeedbackType
	profile.LastFeedbackText = strings.TrimSpace(firstNonEmptyLocal(event.FeedbackText, event.CorrectionText))
	profile.LastFeedbackScore = event.FeedbackScore
	profile.LastFeedbackAt = event.CreatedAt
	profile.LastQueryTextDigest = digestTextLocal(event.QueryText)
	profile.LastAnswerTextDigest = digestTextLocal(event.AnswerText)
	profile.UpdatedAt = event.CreatedAt
	if profile.ReasonCodeCounts == nil {
		profile.ReasonCodeCounts = map[string]int64{}
	}
	if strings.TrimSpace(event.FeedbackType) != "" || event.FeedbackScore != 0 || strings.TrimSpace(event.FeedbackText) != "" {
		profile.TotalFeedbackCount++
	}
	switch strings.TrimSpace(event.FeedbackType) {
	case "thumbs_up":
		profile.PositiveFeedbackCount++
	case "thumbs_down":
		profile.NegativeFeedbackCount++
	case "text":
		profile.TextFeedbackCount++
	}
	if strings.TrimSpace(priority) == "high" {
		profile.HighPriorityCount++
	} else if strings.TrimSpace(priority) == "medium" {
		profile.MediumPriorityCount++
	}
	for _, reason := range sanitizeReasonsLocal(event.ExplicitReasonCodes) {
		profile.ReasonCodeCounts[reason]++
	}
	s.profiles[event.UserID] = profile
	return nil
}

func (s *MemoryLearningProfileStore) ProjectScorecard(_ context.Context, score assistant.Scorecard, priority string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if strings.TrimSpace(score.UserID) == "" || strings.TrimSpace(score.MetricID) == "" {
		return nil
	}
	profile := s.profiles[score.UserID]
	profile.UserID = score.UserID
	profile.LastRunID = score.RunID
	profile.LastMetricID = score.MetricID
	profile.LastMetricScore = score.ScoreValue
	profile.UpdatedAt = score.CreatedAt
	if profile.MetricSampleCounts == nil {
		profile.MetricSampleCounts = map[string]int64{}
	}
	if profile.MetricScoreSums == nil {
		profile.MetricScoreSums = map[string]float64{}
	}
	if profile.LatestMetricScores == nil {
		profile.LatestMetricScores = map[string]float64{}
	}
	profile.MetricSampleCounts[score.MetricID]++
	profile.MetricScoreSums[score.MetricID] += score.ScoreValue
	profile.LatestMetricScores[score.MetricID] = score.ScoreValue
	if strings.TrimSpace(priority) == "high" {
		profile.HighPriorityCount++
	} else if strings.TrimSpace(priority) == "medium" {
		profile.MediumPriorityCount++
	}
	s.profiles[score.UserID] = profile
	return nil
}

func (s *MemoryLearningProfileStore) GetLearningProfile(_ context.Context, userID string) (*assistant.AssistantLearningProfile, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	profile, ok := s.profiles[userID]
	if !ok {
		return nil, nil
	}
	copy := profile
	return &copy, nil
}

func (s *MemoryLearningProfileStore) BuildMemoryItems(ctx context.Context, userID string, limit int) ([]assistant.AssistantUserMemoryView, error) {
	profile, err := s.GetLearningProfile(ctx, userID)
	if err != nil || profile == nil {
		return nil, err
	}
	return buildMemoryItemsFromProfile(profile, limit), nil
}

func (s *MemoryLearningProfileStore) BuildTaskItems(ctx context.Context, userID string, now time.Time) ([]assistant.AssistantUserTaskView, error) {
	profile, err := s.GetLearningProfile(ctx, userID)
	if err != nil || profile == nil {
		return nil, err
	}
	return buildTaskItemsFromProfile(profile, now), nil
}

func buildMemoryItemsFromProfile(profile *assistant.AssistantLearningProfile, limit int) []assistant.AssistantUserMemoryView {
	items := make([]assistant.AssistantUserMemoryView, 0, 3)
	if profile == nil {
		return items
	}
	if strings.TrimSpace(profile.LastFeedbackType) != "" || strings.TrimSpace(profile.LastFeedbackText) != "" {
		snippet := strings.TrimSpace(profile.LastFeedbackText)
		if snippet == "" {
			snippet = fmt.Sprintf("最近一次反馈类型：%s，分值 %.1f。", profile.LastFeedbackType, profile.LastFeedbackScore)
		}
		items = append(items, assistant.AssistantUserMemoryView{
			MemoryID:   "learning:last-feedback:" + profile.UserID,
			Title:      "最近反馈偏好",
			Snippet:    trimSnippetLocal(snippet, 80),
			SourceType: "learning_profile",
			CreatedAt:  profile.LastFeedbackAt.Format(time.RFC3339),
			UpdatedAt:  profile.UpdatedAt.Format(time.RFC3339),
		})
	}
	if len(profile.ReasonCodeCounts) > 0 {
		topReasons := topReasonCodesLocal(profile.ReasonCodeCounts, 3)
		items = append(items, assistant.AssistantUserMemoryView{
			MemoryID:   "learning:reason-codes:" + profile.UserID,
			Title:      "高频反馈原因",
			Snippet:    "最近高频原因：" + strings.Join(topReasons, "、"),
			SourceType: "learning_profile",
			CreatedAt:  profile.UpdatedAt.Format(time.RFC3339),
			UpdatedAt:  profile.UpdatedAt.Format(time.RFC3339),
		})
	}
	if len(profile.LatestMetricScores) > 0 {
		metricID, scoreValue := topLatestMetricLocal(profile.LatestMetricScores)
		items = append(items, assistant.AssistantUserMemoryView{
			MemoryID:   "learning:last-metric:" + profile.UserID,
			Title:      "最近评分卡摘要",
			Snippet:    fmt.Sprintf("%s 最新分值 %.1f。", metricID, scoreValue),
			SourceType: "scorecard_projection",
			CreatedAt:  profile.UpdatedAt.Format(time.RFC3339),
			UpdatedAt:  profile.UpdatedAt.Format(time.RFC3339),
		})
	}
	if limit > 0 && len(items) > limit {
		items = items[:limit]
	}
	return items
}

func buildTaskItemsFromProfile(profile *assistant.AssistantLearningProfile, now time.Time) []assistant.AssistantUserTaskView {
	items := []assistant.AssistantUserTaskView{}
	if profile == nil {
		return items
	}
	if profile.NegativeFeedbackCount > 0 || profile.HighPriorityCount > 0 {
		items = append(items, assistant.AssistantUserTaskView{
			TaskID:        "assistant-review-learning-profile",
			Title:         "复盘近期负反馈",
			Description:   fmt.Sprintf("近期负反馈 %d 次，高优先级信号 %d 次。", profile.NegativeFeedbackCount, profile.HighPriorityCount),
			Status:        "pending",
			Priority:      "high",
			SourceSkillID: "assistant_learning",
			UpdatedAt:     now.Format(time.RFC3339),
		})
	}
	if len(profile.LatestMetricScores) > 0 {
		metricID, scoreValue := topLatestMetricLocal(profile.LatestMetricScores)
		status := "in_progress"
		priority := "medium"
		if scoreValue <= 2 {
			status = "pending"
			priority = "high"
		}
		items = append(items, assistant.AssistantUserTaskView{
			TaskID:        "assistant-followup-metric-" + metricID,
			Title:         "检查关键评分卡",
			Description:   fmt.Sprintf("指标 %s 当前最新分值 %.1f，建议继续跟踪。", metricID, scoreValue),
			Status:        status,
			Priority:      priority,
			SourceSkillID: "assistant_learning",
			UpdatedAt:     now.Format(time.RFC3339),
		})
	}
	return items
}

func firstNonEmptyLocal(values ...string) string {
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			return trimmed
		}
	}
	return ""
}

func digestTextLocal(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}
	sum := sha1.Sum([]byte(trimmed))
	return hex.EncodeToString(sum[:])
}

func sanitizeReasonsLocal(items []string) []string {
	out := make([]string, 0, len(items))
	seen := map[string]struct{}{}
	for _, item := range items {
		trimmed := strings.TrimSpace(item)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		out = append(out, trimmed)
	}
	return out
}

func trimSnippetLocal(raw string, limit int) string {
	text := strings.TrimSpace(raw)
	if limit <= 0 || len(text) <= limit {
		return text
	}
	return text[:limit]
}

func topReasonCodesLocal(counts map[string]int64, limit int) []string {
	type pair struct {
		key   string
		count int64
	}
	items := make([]pair, 0, len(counts))
	for key, count := range counts {
		items = append(items, pair{key: key, count: count})
	}
	sort.Slice(items, func(i, j int) bool {
		if items[i].count == items[j].count {
			return items[i].key < items[j].key
		}
		return items[i].count > items[j].count
	})
	if limit <= 0 || limit > len(items) {
		limit = len(items)
	}
	out := make([]string, 0, limit)
	for _, item := range items[:limit] {
		out = append(out, item.key)
	}
	return out
}

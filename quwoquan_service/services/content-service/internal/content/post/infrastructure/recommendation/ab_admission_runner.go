package recommendation

// N1-3 AB 准入周期任务：EvaluateAndRecordABAdmission 此前实现完备但生产零调用
// （P0-G「最后一公里」断裂），ab_experiment_validity SLI 与 RecommendationABValidityLow
// 告警无数据。本 runner 周期性从 rec_learning_events 聚合每个 enabled 实验的
// bucket 观测（samples=rec_impression，conversions=rec_engagement click），
// 喂 EvaluateAndRecordABAdmission → recommendation_feed_ab_experiment_validity_total。
//
// bucket 归属：
//   - rec_model_vs_rule：impression 事实自带 context.modelBucket（下发时真实分桶）；
//   - 其他实验（scoring weights 等）：按当前 policy 确定性 hash 重算 userId 分桶
//     （与 engine 同一 AssignBucket；窗口内 policy 变更会引入少量归属漂移，
//     SRM 检查会暴露异常，S0 体量可接受）。

import (
	"context"
	"log/slog"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtrec "quwoquan_service/runtime/recommendation"
	recpolicy "quwoquan_service/runtime/recpolicy"
)

type ABAdmissionRunner struct {
	events *mongo.Collection
	policy *recpolicy.Store
	logger *slog.Logger
	window time.Duration
}

type abLearningEventRow struct {
	UserID   string            `bson:"userId"`
	TargetID string            `bson:"targetId"`
	Context  map[string]any    `bson:"context"`
	Labels   map[string]string `bson:"labels"`
}

func NewABAdmissionRunner(db *mongo.Database, policy *recpolicy.Store, logger *slog.Logger) *ABAdmissionRunner {
	if logger == nil {
		logger = slog.Default()
	}
	return &ABAdmissionRunner{
		events: db.Collection("rec_learning_events"),
		policy: policy,
		logger: logger,
		window: 24 * time.Hour,
	}
}

// RunOnce 对当前 policy 全部 enabled 实验执行一轮准入评估并记账。
func (r *ABAdmissionRunner) RunOnce(ctx context.Context) []rtrec.ABAdmissionResult {
	if r == nil || r.events == nil || r.policy == nil {
		return nil
	}
	policy := r.policy.Current()
	results := make([]rtrec.ABAdmissionResult, 0, len(policy.Experiments))
	for _, exp := range policy.Experiments {
		if !exp.Enabled || len(exp.Buckets) == 0 {
			continue
		}
		obs, err := r.ObserveExperiment(ctx, policy, exp)
		if err != nil {
			r.logger.Warn("ab admission observation failed",
				slog.String("experiment", exp.ID), slog.String("err", err.Error()))
			continue
		}
		result := rtrec.EvaluateAndRecordABAdmission(obs, policy.ABAdmission)
		results = append(results, result)
		r.logger.Info("ab admission evaluated",
			slog.String("experiment", exp.ID),
			slog.Bool("valid", result.Valid),
			slog.Any("reasons", result.Reasons),
			slog.Any("rollbackCandidates", result.RollbackCandidates))
	}
	return results
}

// Run 周期执行（默认每小时）直到 ctx 结束。
func (r *ABAdmissionRunner) Run(ctx context.Context, interval time.Duration) {
	if r == nil {
		return
	}
	if interval <= 0 {
		interval = time.Hour
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		r.RunOnce(ctx)
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

// ObserveExperiment 聚合窗口内单实验的 bucket 观测。
func (r *ABAdmissionRunner) ObserveExperiment(
	ctx context.Context,
	policy *recpolicy.RecPolicy,
	exp recpolicy.ExperimentDef,
) (rtrec.ABExperimentObservation, error) {
	since := time.Now().UTC().Add(-r.window).Format(time.RFC3339)

	// samples：窗口内 rec_impression。
	impressionCursor, err := r.events.Find(ctx, bson.M{
		"eventType":  "rec_impression",
		"scenario":   "content_feed",
		"occurredAt": bson.M{"$gte": since},
	})
	if err != nil {
		return rtrec.ABExperimentObservation{}, err
	}
	var impressions []abLearningEventRow
	if err := impressionCursor.All(ctx, &impressions); err != nil {
		return rtrec.ABExperimentObservation{}, err
	}

	// conversions：窗口内 rec_engagement 且 action=click（primary metric CTR 分子）。
	// 只接纳携带 feedRequestId 的推荐流点击；搜索页/资料页等复用行为 tracker 的点击
	// 不能进入推荐实验分子。
	engagementCursor, err := r.events.Find(ctx, bson.M{
		"eventType":             "rec_engagement",
		"scenario":              "content_feed",
		"occurredAt":            bson.M{"$gte": since},
		"labels.action":         "click",
		"context.feedRequestId": bson.M{"$exists": true, "$ne": ""},
	})
	if err != nil {
		return rtrec.ABExperimentObservation{}, err
	}
	var engagements []abLearningEventRow
	if err := engagementCursor.All(ctx, &engagements); err != nil {
		return rtrec.ABExperimentObservation{}, err
	}

	samples, conversions := aggregateABObservation(policy, exp, impressions, engagements)

	obs := rtrec.ABExperimentObservation{
		ExperimentID:  exp.ID,
		ControlBucket: ControlBucketFor(exp),
	}
	for _, bucket := range exp.Buckets {
		obs.Buckets = append(obs.Buckets, rtrec.BucketObservation{
			Bucket:      bucket.Name,
			DesignPct:   bucket.WeightPct,
			Samples:     samples[bucket.Name],
			Conversions: conversions[bucket.Name],
		})
	}
	return obs, nil
}

// aggregateABObservation 先以曝光事实确定实验桶，再用 feedRequestId+targetId
// 将 click 严格回连到同一条 served/impression。rec_engagement 不携带
// modelBucket，若直接从点击事件读取，model-vs-rule 的 conversions 会恒为 0；
// 若仅按 user 重算，则非 feed 点击和策略变更都会污染实验。
func aggregateABObservation(
	policy *recpolicy.RecPolicy,
	exp recpolicy.ExperimentDef,
	impressions []abLearningEventRow,
	engagements []abLearningEventRow,
) (map[string]int, map[string]int) {
	samples := map[string]int{}
	conversions := map[string]int{}
	impressionBuckets := make(map[string]string, len(impressions))

	for _, row := range impressions {
		bucket := resolveImpressionBucket(policy, exp, row)
		key := abAttributionKey(row)
		if bucket == "" || key == "" {
			continue
		}
		samples[bucket]++
		impressionBuckets[key] = bucket
	}
	for _, row := range engagements {
		if bucket := impressionBuckets[abAttributionKey(row)]; bucket != "" {
			conversions[bucket]++
		}
	}
	return samples, conversions
}

func resolveImpressionBucket(
	policy *recpolicy.RecPolicy,
	exp recpolicy.ExperimentDef,
	row abLearningEventRow,
) string {
	if exp.ID == recpolicy.ExpModelVsRule {
		if raw, ok := row.Context["modelBucket"].(string); ok {
			return strings.TrimSpace(raw)
		}
		return ""
	}
	bucket, ok := policy.ResolveBucket(exp.ID, row.UserID, nil)
	if !ok {
		return ""
	}
	return bucket
}

func abAttributionKey(row abLearningEventRow) string {
	rawFeedRequestID, _ := row.Context["feedRequestId"].(string)
	feedRequestID := strings.TrimSpace(rawFeedRequestID)
	targetID := strings.TrimSpace(row.TargetID)
	if feedRequestID == "" || targetID == "" {
		return ""
	}
	return feedRequestID + "\x00" + targetID
}

// ControlBucketFor selects the stable control bucket for an experiment.
// It prefers explicit control/rule buckets and otherwise uses the heaviest
// configured bucket so callers share one admission-policy interpretation.
func ControlBucketFor(exp recpolicy.ExperimentDef) string {
	best := ""
	bestPct := -1
	for _, bucket := range exp.Buckets {
		switch bucket.Name {
		case "control", "rule":
			return bucket.Name
		}
		if bucket.WeightPct > bestPct {
			best, bestPct = bucket.Name, bucket.WeightPct
		}
	}
	return best
}

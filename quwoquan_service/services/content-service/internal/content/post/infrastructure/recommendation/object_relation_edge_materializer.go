package recommendation

import (
	"context"
	"fmt"
	"log/slog"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
)

// W10 关系图谱自动物化（B22）：图谱 = 运行库中可自动物化、可衰减退场、带
// confidence + evidenceRefs 的边表投影（rm_object_relation_edges）。
// 全部边从已有信号派生（零人工标注、零图数据库、零请求期图遍历）：
//   - semantic_co_mention【S0】：同一 published post 的 entityMentions 实体对共现。
//   - tag_overlap【S0】：entities 档案 tagRefs 交集（graph.py 算法进运行库正式链路）。
//   - geo_proximity【S0】：entities conditionProfile.regions 同域确定性计算。
//   - social/intersection 边【S0 已落地保持】：既有 Graph 边权 materializer（独立轨）。
//   - behavior_co_engagement【S1 仅 schema】：见 BehaviorCoEngagementEdgeType——
//     用户量小时行为共现是噪声，S0 不物化；接口就绪，S1 触发开启不需要重构。
//
// 消费方只读本边表（对象页/推荐/交集同源）；请求期禁止图计算。
const (
	ObjectRelationEdgeCollection = "rm_object_relation_edges"

	SemanticCoMentionEdgeType = "semantic_co_mention"
	TagOverlapEdgeType        = "tag_overlap"
	GeoProximityEdgeType      = "geo_proximity"
	// BehaviorCoEngagementEdgeType 行为共现边（S1 触发物化）：rm_behavior_events
	// 同用户短窗深度互动聚合。S0 只保留类型契约与物化接口。
	BehaviorCoEngagementEdgeType = "behavior_co_engagement"

	ObjectRelationEdgeTTL           = 14 * 24 * time.Hour
	objectRelationEvidenceMax       = 3
	objectRelationMinCoMention      = 1
	objectRelationMinSharedTags     = 2
	objectRelationScanLimit         = 2000
	objectRelationConfidenceEpsilon = 0.01
)

// ObjectRelationEdgeDoc 是边表的存储契约（对齐
// services/entity-service/contracts/entity_homepage/homepage/projections/object_relation_edge.yaml 的
// 消费语义：edgeType/source/target/confidence/evidenceRefs）。
type ObjectRelationEdgeDoc struct {
	EdgeKey      string    `bson:"_id"`
	EdgeType     string    `bson:"edgeType"`
	SourceRef    string    `bson:"sourceRef"`
	TargetRef    string    `bson:"targetRef"`
	Confidence   float64   `bson:"confidence"`
	EvidenceRefs []string  `bson:"evidenceRefs,omitempty"`
	ComputedAt   time.Time `bson:"computedAt"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

// ObjectRelationEdgeMaterializer 周期全量重算内容侧三类边（幂等覆盖写 +
// TTL 退场：本轮未再生的旧边随 expiresAt 过期自动退场，无需人工清理）。
type ObjectRelationEdgeMaterializer struct {
	edgeColl   *mongo.Collection
	postColl   *mongo.Collection
	entityColl *mongo.Collection
	logger     *slog.Logger
	now        func() time.Time
}

func NewObjectRelationEdgeMaterializer(db *mongo.Database, logger *slog.Logger) *ObjectRelationEdgeMaterializer {
	if logger == nil {
		logger = slog.Default()
	}
	return &ObjectRelationEdgeMaterializer{
		edgeColl:   db.Collection(ObjectRelationEdgeCollection),
		postColl:   db.Collection("posts"),
		entityColl: db.Collection("entities"),
		logger:     logger,
		now:        func() time.Time { return time.Now().UTC() },
	}
}

// EnsureIndexes 建 TTL 退场索引与查询索引。
func (m *ObjectRelationEdgeMaterializer) EnsureIndexes(ctx context.Context) error {
	if m == nil || m.edgeColl == nil {
		return nil
	}
	_, err := m.edgeColl.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetExpireAfterSeconds(0),
		},
		{
			Keys: bson.D{{Key: "sourceRef", Value: 1}, {Key: "confidence", Value: -1}},
		},
		{
			Keys: bson.D{{Key: "edgeType", Value: 1}},
		},
	})
	return err
}

// MaterializeAll 全量重算内容侧三类边并覆盖写入。返回各类边数量。
func (m *ObjectRelationEdgeMaterializer) MaterializeAll(ctx context.Context) (map[string]int, error) {
	if m == nil || m.edgeColl == nil {
		return nil, nil
	}
	counts := map[string]int{}
	semantic, err := m.materializeSemanticCoMention(ctx)
	if err != nil {
		return counts, fmt.Errorf("semantic co-mention edges: %w", err)
	}
	counts[SemanticCoMentionEdgeType] = semantic

	tagOverlap, err := m.materializeTagOverlap(ctx)
	if err != nil {
		return counts, fmt.Errorf("tag overlap edges: %w", err)
	}
	counts[TagOverlapEdgeType] = tagOverlap

	geo, err := m.materializeGeoProximity(ctx)
	if err != nil {
		return counts, fmt.Errorf("geo proximity edges: %w", err)
	}
	counts[GeoProximityEdgeType] = geo
	return counts, nil
}

// Run 周期物化（与 raw-affinity decay 同模式的常驻 goroutine 入口）。
func (m *ObjectRelationEdgeMaterializer) Run(ctx context.Context, interval time.Duration) {
	if m == nil || interval <= 0 {
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		counts, err := m.MaterializeAll(ctx)
		// N1-2：物化结果记账（连续失败 + 边表 14 天 TTL = 边表静默清空，
		// last_success gauge 停滞由告警承接）。
		rtrec.RecordEdgeMaterializerRun("all", err)
		if err != nil {
			m.logger.Warn("object relation edge materialize failed", slog.String("err", err.Error()))
		} else {
			m.logger.Info("object relation edges materialized",
				slog.Int("semantic", counts[SemanticCoMentionEdgeType]),
				slog.Int("tagOverlap", counts[TagOverlapEdgeType]),
				slog.Int("geo", counts[GeoProximityEdgeType]))
		}
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
		}
	}
}

func (m *ObjectRelationEdgeMaterializer) materializeSemanticCoMention(ctx context.Context) (int, error) {
	cursor, err := m.postColl.Find(ctx,
		bson.M{"status": "published", "entityMentions.0": bson.M{"$exists": true}},
		options.Find().
			SetProjection(bson.M{"entityMentions.subjectId": 1}).
			SetLimit(objectRelationScanLimit),
	)
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)
	var docs []struct {
		ID             string `bson:"_id"`
		EntityMentions []struct {
			SubjectID string `bson:"subjectId"`
		} `bson:"entityMentions"`
	}
	if err := cursor.All(ctx, &docs); err != nil {
		return 0, err
	}
	type pairAgg struct {
		count    int
		evidence []string
	}
	pairs := map[[2]string]*pairAgg{}
	maxCount := 0
	for _, doc := range docs {
		refs := uniqueSortedRefs(doc.EntityMentions)
		for i := 0; i < len(refs); i++ {
			for j := i + 1; j < len(refs); j++ {
				key := [2]string{refs[i], refs[j]}
				agg := pairs[key]
				if agg == nil {
					agg = &pairAgg{}
					pairs[key] = agg
				}
				agg.count++
				if len(agg.evidence) < objectRelationEvidenceMax {
					agg.evidence = append(agg.evidence, doc.ID)
				}
				if agg.count > maxCount {
					maxCount = agg.count
				}
			}
		}
	}
	written := 0
	for key, agg := range pairs {
		if agg.count < objectRelationMinCoMention {
			continue
		}
		confidence := float64(agg.count) / float64(maxCount)
		if confidence < objectRelationConfidenceEpsilon {
			continue
		}
		if err := m.upsertEdgePair(ctx, SemanticCoMentionEdgeType, key[0], key[1], confidence, agg.evidence); err != nil {
			return written, err
		}
		written += 2
	}
	return written, nil
}

func (m *ObjectRelationEdgeMaterializer) materializeTagOverlap(ctx context.Context) (int, error) {
	entities, err := m.loadEntityProfiles(ctx)
	if err != nil {
		return 0, err
	}
	written := 0
	maxShared := 0
	type overlap struct {
		a, b   string
		shared []string
	}
	var overlaps []overlap
	for i := 0; i < len(entities); i++ {
		for j := i + 1; j < len(entities); j++ {
			shared := SharedStrings(entities[i].TagRefs, entities[j].TagRefs)
			if len(shared) < objectRelationMinSharedTags {
				continue
			}
			overlaps = append(overlaps, overlap{
				a: entities[i].EntityRef, b: entities[j].EntityRef, shared: shared,
			})
			if len(shared) > maxShared {
				maxShared = len(shared)
			}
		}
	}
	for _, o := range overlaps {
		confidence := float64(len(o.shared)) / float64(maxShared)
		evidence := o.shared
		if len(evidence) > objectRelationEvidenceMax {
			evidence = evidence[:objectRelationEvidenceMax]
		}
		if err := m.upsertEdgePair(ctx, TagOverlapEdgeType, o.a, o.b, confidence, evidence); err != nil {
			return written, err
		}
		written += 2
	}
	return written, nil
}

func (m *ObjectRelationEdgeMaterializer) materializeGeoProximity(ctx context.Context) (int, error) {
	entities, err := m.loadEntityProfiles(ctx)
	if err != nil {
		return 0, err
	}
	byRegion := map[string][]string{}
	for _, entity := range entities {
		for _, region := range entity.Regions {
			region = strings.TrimSpace(region)
			if region == "" {
				continue
			}
			byRegion[region] = append(byRegion[region], entity.EntityRef)
		}
	}
	written := 0
	seen := map[[2]string]bool{}
	for region, refs := range byRegion {
		refs = dedupeStrings(refs)
		sort.Strings(refs)
		for i := 0; i < len(refs); i++ {
			for j := i + 1; j < len(refs); j++ {
				key := [2]string{refs[i], refs[j]}
				if seen[key] {
					continue
				}
				seen[key] = true
				// 同域确定性边：confidence 固定 1.0（事实边，非概率），evidence 为域名。
				if err := m.upsertEdgePair(ctx, GeoProximityEdgeType, refs[i], refs[j], 1.0, []string{region}); err != nil {
					return written, err
				}
				written += 2
			}
		}
	}
	return written, nil
}

type entityProfileDoc struct {
	EntityRef string   `bson:"entityRef"`
	TagRefs   []string `bson:"tagRefs"`
	Regions   []string `bson:"-"`
}

func (m *ObjectRelationEdgeMaterializer) loadEntityProfiles(ctx context.Context) ([]entityProfileDoc, error) {
	cursor, err := m.entityColl.Find(ctx,
		bson.M{"hasPage": true},
		options.Find().
			SetProjection(bson.M{"entityRef": 1, "tagRefs": 1, "conditionProfile": 1}).
			SetLimit(objectRelationScanLimit),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var raw []struct {
		EntityRef        string         `bson:"entityRef"`
		TagRefs          []string       `bson:"tagRefs"`
		ConditionProfile map[string]any `bson:"conditionProfile"`
	}
	if err := cursor.All(ctx, &raw); err != nil {
		return nil, err
	}
	out := make([]entityProfileDoc, 0, len(raw))
	for _, doc := range raw {
		if strings.TrimSpace(doc.EntityRef) == "" {
			continue
		}
		out = append(out, entityProfileDoc{
			EntityRef: doc.EntityRef,
			TagRefs:   doc.TagRefs,
			Regions:   stringSliceFromAny(doc.ConditionProfile["regions"]),
		})
	}
	return out, nil
}

// upsertEdgePair 双向写入（source→target 与 target→source 各一条），保证按
// sourceRef 查询单索引可达。_id 由 (edgeType, source, target) 确定，天然幂等。
func (m *ObjectRelationEdgeMaterializer) upsertEdgePair(
	ctx context.Context,
	edgeType, refA, refB string,
	confidence float64,
	evidence []string,
) error {
	now := m.now()
	expires := now.Add(ObjectRelationEdgeTTL)
	for _, pair := range [][2]string{{refA, refB}, {refB, refA}} {
		doc := ObjectRelationEdgeDoc{
			EdgeKey:      edgeType + "|" + pair[0] + "|" + pair[1],
			EdgeType:     edgeType,
			SourceRef:    pair[0],
			TargetRef:    pair[1],
			Confidence:   confidence,
			EvidenceRefs: evidence,
			ComputedAt:   now,
			ExpiresAt:    expires,
		}
		_, err := m.edgeColl.ReplaceOne(ctx,
			bson.M{"_id": doc.EdgeKey},
			doc,
			options.Replace().SetUpsert(true),
		)
		if err != nil {
			return err
		}
	}
	return nil
}

func uniqueSortedRefs(mentions []struct {
	SubjectID string `bson:"subjectId"`
}) []string {
	set := map[string]bool{}
	for _, mention := range mentions {
		ref := strings.TrimSpace(mention.SubjectID)
		if ref != "" {
			set[ref] = true
		}
	}
	out := make([]string, 0, len(set))
	for ref := range set {
		out = append(out, ref)
	}
	sort.Strings(out)
	return out
}

func SharedStrings(a, b []string) []string {
	setA := map[string]bool{}
	for _, item := range a {
		item = strings.TrimSpace(item)
		if item != "" {
			setA[item] = true
		}
	}
	var shared []string
	seen := map[string]bool{}
	for _, item := range b {
		item = strings.TrimSpace(item)
		if item != "" && setA[item] && !seen[item] {
			shared = append(shared, item)
			seen[item] = true
		}
	}
	sort.Strings(shared)
	return shared
}

func dedupeStrings(items []string) []string {
	seen := map[string]bool{}
	out := make([]string, 0, len(items))
	for _, item := range items {
		if !seen[item] {
			seen[item] = true
			out = append(out, item)
		}
	}
	return out
}

func stringSliceFromAny(raw any) []string {
	switch items := raw.(type) {
	case []string:
		return items
	case []any:
		out := make([]string, 0, len(items))
		for _, item := range items {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	case bson.A:
		out := make([]string, 0, len(items))
		for _, item := range items {
			if s, ok := item.(string); ok {
				out = append(out, s)
			}
		}
		return out
	default:
		return nil
	}
}

// ObjectRelationEdgeReader 是边表的统一读端口：对象页/推荐/交集消费方只读
// 本接口，禁止请求期图遍历或第二套关联表。
type ObjectRelationEdgeReader struct {
	coll *mongo.Collection
}

func NewObjectRelationEdgeReader(db *mongo.Database) *ObjectRelationEdgeReader {
	return &ObjectRelationEdgeReader{coll: db.Collection(ObjectRelationEdgeCollection)}
}

// EdgesFrom 返回 sourceRef 出发的 Top-N 边（按 confidence 降序）。
func (r *ObjectRelationEdgeReader) EdgesFrom(
	ctx context.Context,
	sourceRef string,
	limit int,
) ([]ObjectRelationEdgeDoc, error) {
	if r == nil || r.coll == nil || strings.TrimSpace(sourceRef) == "" || limit <= 0 {
		return nil, nil
	}
	cursor, err := r.coll.Find(ctx,
		bson.M{"sourceRef": strings.TrimSpace(sourceRef)},
		options.Find().
			SetSort(bson.D{{Key: "confidence", Value: -1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var edges []ObjectRelationEdgeDoc
	if err := cursor.All(ctx, &edges); err != nil {
		return nil, err
	}
	return edges, nil
}

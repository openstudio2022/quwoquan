package recommendation

import (
	"context"
	"sort"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtrec "quwoquan_service/runtime/recommendation"
	generated "quwoquan_service/services/content-service/generated/content/post"
	"quwoquan_service/services/content-service/internal/content/post/application/identity"
	intersectionapp "quwoquan_service/services/content-service/internal/content/post/application/intersection"
)

// IntersectionRecallPath 是交集召回通道的通道名（观测与配额都按它统计）。
const IntersectionRecallPath = "intersection_edge"

// maxIntersectionRecallSeeds 单次召回使用的种子对象上限：按边权取最强的若干条，
// 保证 $in 谓词有界，避免快照异常膨胀时打出无界查询。
const maxIntersectionRecallSeeds = 40

// IntersectionEdgeRecallSource 把交集从「排后附着的解释」升级为「召回通道」。
//
// 种子来自 viewer 的事实交集快照（rm_viewer_object_intersection）：取边权最强的
// 若干对象，再按两种连接方式取内容——对象是人时取其作品（authorId），对象是
// 地点/实体/圈子时取挂了该对象的内容（entityRefs）。因此进入 feed 的不再只是
// 「被别的通道召回后恰好能解释成交集」的内容，交集本身就能决定供给。
//
// 边界：
//   - 匿名 viewer 跳过（无交集快照，也不该把陌生人关系带进公共 feed）。
//   - deferred kind 的边不做种子：注册表标 deferred 表示可证数据源缺位，
//     展示与排序都已拦住，召回同样不得借历史快照复活。
//   - 强度不在这里注入。候选的事实交集强度统一由 UserFeatureVector.IntersectionEdges
//     在排序期匹配，保证「同一条边只有一个真相源」，也让其他通道召回的同对象内容
//     拿到同样的强度。
type IntersectionEdgeRecallSource struct {
	feedColl *mongo.Collection
	edges    ViewerIntersectionReadModel
}

// IsDeferredIntersectionKind 是 deferred 判定的唯一入口，召回、排序特征与测试
// 共用同一口径，避免各处自行拼注册表查询。
func IsDeferredIntersectionKind(kind string) bool {
	_, deferred := generated.IntersectionDeferredKinds[strings.TrimSpace(kind)]
	return deferred
}

func NewIntersectionEdgeRecallSource(
	db *mongo.Database,
	edges ViewerIntersectionReadModel,
) *IntersectionEdgeRecallSource {
	return &IntersectionEdgeRecallSource{
		feedColl: db.Collection("rm_discovery_feed"),
		edges:    edges,
	}
}

func (s *IntersectionEdgeRecallSource) Recall(
	ctx context.Context,
	req rtrec.RecallRequest,
) ([]rtrec.ContentCandidate, error) {
	if s == nil || s.edges == nil {
		return nil, rtrec.SkipRecall("intersection recall requires the viewer intersection read model")
	}
	viewerID := strings.TrimSpace(req.UserID)
	if viewerID == "" || viewerID == identity.AnonymousFallbackPersonaID {
		return nil, rtrec.SkipRecall("intersection recall requires an authenticated persona")
	}
	doc, ok, err := s.edges.Load(ctx, viewerID)
	if err != nil {
		return nil, err
	}
	if !ok || len(doc.Reasons) == 0 {
		return nil, rtrec.SkipRecall("viewer has no materialized intersection edges")
	}

	people, objects := IntersectionRecallSeeds(doc.Reasons, maxIntersectionRecallSeeds)
	if len(people) == 0 && len(objects) == 0 {
		return nil, rtrec.SkipRecall("no eligible intersection seeds")
	}

	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	connectors := make(bson.A, 0, 2)
	if len(people) > 0 {
		connectors = append(connectors, bson.M{"authorId": bson.M{"$in": people}})
	}
	if len(objects) > 0 {
		connectors = append(connectors, bson.M{"entityRefs": bson.M{"$in": objects}})
	}
	filter := bson.M{"$and": bson.A{bson.M{"$or": connectors}}}
	applyReleaseServingEligibility(filter, req.ActiveReleaseID, req.ActiveManifestDigest)
	applyVerticalFilter(filter, req.Vertical)
	// applyReleaseServingEligibility 也可能写 $or（发布可服务性）。两个 $or 不能
	// 在同一层共存，所以把交集连接谓词收进 $and，发布谓词保留在顶层。
	if release, hasRelease := filter["$or"]; hasRelease {
		filter["$and"] = append(filter["$and"].(bson.A), bson.M{"$or": release})
		delete(filter, "$or")
	}

	opts := options.Find().
		SetSort(bson.D{
			{Key: "recScore", Value: -1},
			{Key: "publishedAt", Value: -1},
			{Key: "postId", Value: -1},
		}).
		SetLimit(int64(limit))

	candidates, err := queryDiscoveryFeed(ctx, s.feedColl, filter, opts, IntersectionRecallPath)
	if err != nil {
		return nil, err
	}
	// 自己的内容不构成「你和 TA 的交集」。
	out := make([]rtrec.ContentCandidate, 0, len(candidates))
	for _, c := range candidates {
		if strings.TrimSpace(c.AuthorID) == viewerID {
			continue
		}
		out = append(out, c)
	}
	return out, nil
}

// IntersectionRecallSeeds 是本通道的准入策略：从 viewer 快照里挑出可用种子，
// 按边权降序截断，返回人对象（走 authorId 连接）与非人对象（走 entityRefs 连接）两组。
// 导出是为了让合约测试直接锁住准入口径（deferred 过滤、零权丢弃、按边权截断），
// 而不是靠一次 Mongo 查询间接推断。
func IntersectionRecallSeeds(
	reasons []intersectionapp.IntersectionReasonView,
	limit int,
) (people []string, objects []string) {
	type seed struct {
		id     string
		person bool
		weight float64
	}
	best := make(map[string]seed, len(reasons))
	for _, reason := range reasons {
		kind := strings.TrimSpace(reason.Kind)
		if kind == "" {
			kind = strings.TrimSpace(reason.Source)
		}
		if IsDeferredIntersectionKind(kind) {
			continue
		}
		if reason.EdgeWeight <= 0 {
			continue
		}
		objectID := strings.TrimSpace(reason.ActionTargetID)
		if objectID == "" {
			objectID = strings.TrimSpace(reason.RelationObjectID)
		}
		if objectID == "" {
			continue
		}
		candidate := seed{
			id:     objectID,
			person: strings.TrimSpace(reason.ObjectKind) == "person",
			weight: reason.EdgeWeight,
		}
		if existing, seen := best[objectID]; seen && existing.weight >= candidate.weight {
			continue
		}
		best[objectID] = candidate
	}
	ordered := make([]seed, 0, len(best))
	for _, s := range best {
		ordered = append(ordered, s)
	}
	sort.SliceStable(ordered, func(i, j int) bool {
		if ordered[i].weight != ordered[j].weight {
			return ordered[i].weight > ordered[j].weight
		}
		return ordered[i].id < ordered[j].id
	})
	if limit > 0 && len(ordered) > limit {
		ordered = ordered[:limit]
	}
	for _, s := range ordered {
		if s.person {
			people = append(people, s.id)
		} else {
			objects = append(objects, s.id)
		}
	}
	return people, objects
}

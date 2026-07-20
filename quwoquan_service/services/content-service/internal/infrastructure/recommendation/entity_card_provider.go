package recommendation

import (
	"context"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	feedapp "quwoquan_service/services/content-service/internal/application/feed"
)

const (
	EntityCardObjectKind = "entity_homepage"
	EntityCardRecallPath = "entity_card_affinity"

	entityCardWishlistWeight   = 3.0
	entityCardAffinityMinScore = 0.05
	entityCardWishlistWindow   = 90 * 24 * time.Hour
	entityCardScanLimit        = 400
)

// MongoEntityCardProvider 是 S0 混合推荐的实体主页卡召回器（B4 阶段一）：
// 只读三个既有物化集合——viewer 的实体实例亲和（rm_recommend_feature，
// EntityInterestPropagation 投影产物）、显式「想去」意图（entity_wishlist_events）
// 与数据工程灌库的实体档案（entities，hasPage=true 才可作为可点击对象卡）。
// 读路径零同步打分、零跨服务调用（RecommendationAffinity 投影转生产的 S0 形态：
// viewer×entity Top-N 由既有特征在线求并，行为共现边物化后（W10/S1）切换消费边表）。
type MongoEntityCardProvider struct {
	featureColl  *mongo.Collection
	wishlistColl *mongo.Collection
	entityColl   *mongo.Collection
	postColl     *mongo.Collection
	now          func() time.Time
}

func NewMongoEntityCardProvider(db *mongo.Database) *MongoEntityCardProvider {
	return &MongoEntityCardProvider{
		featureColl:  db.Collection("rm_recommend_feature"),
		wishlistColl: db.Collection("entity_wishlist_events"),
		entityColl:   db.Collection("entities"),
		postColl:     db.Collection("posts"),
		now:          func() time.Time { return time.Now().UTC() },
	}
}

type entityCardCandidate struct {
	entityRef string
	score     float64
	reason    string
}

func (p *MongoEntityCardProvider) ObjectCards(
	ctx context.Context,
	userID string,
	limit int,
) ([]feedapp.ObjectCardView, error) {
	if p == nil || strings.TrimSpace(userID) == "" || limit <= 0 {
		return nil, nil
	}
	byRef := map[string]*entityCardCandidate{}

	// 信号 1：实体实例亲和（行为回流经 EntityInterestPropagation 投影）。
	var featureDoc struct {
		EntityInstanceAffinities map[string]float64 `bson:"entityInstanceAffinities"`
	}
	err := p.featureColl.FindOne(
		ctx,
		bson.M{"userId": strings.TrimSpace(userID)},
		options.FindOne().SetProjection(bson.M{"entityInstanceAffinities": 1}),
	).Decode(&featureDoc)
	if err != nil && err != mongo.ErrNoDocuments {
		return nil, err
	}
	for entityRef, score := range featureDoc.EntityInstanceAffinities {
		if score < entityCardAffinityMinScore {
			continue
		}
		byRef[entityRef] = &entityCardCandidate{
			entityRef: entityRef,
			score:     score,
			reason:    "affinity",
		}
	}

	// 信号 2：显式「想去」（coWishlistedEntity 的真实意图源，权重强于隐式亲和）。
	// 字段契约与 MongoWishlistEventStore 写入 schema 对齐（N2-2 修复漂移：
	// entityId/status/updatedAt，此前误查 entityRef/state/occurredAt 恒空）。
	wishlistCursor, err := p.wishlistColl.Find(
		ctx,
		bson.M{
			"userId":    strings.TrimSpace(userID),
			"status":    bson.M{"$ne": "removed"},
			"updatedAt": bson.M{"$gte": p.now().Add(-entityCardWishlistWindow)},
		},
		options.Find().
			SetProjection(bson.M{"entityId": 1}).
			SetSort(bson.D{{Key: "updatedAt", Value: -1}}).
			SetLimit(entityCardScanLimit),
	)
	if err == nil {
		var wishDocs []struct {
			EntityID string `bson:"entityId"`
		}
		if err := wishlistCursor.All(ctx, &wishDocs); err == nil {
			for _, doc := range wishDocs {
				ref := strings.TrimSpace(doc.EntityID)
				if ref == "" {
					continue
				}
				if existing, ok := byRef[ref]; ok {
					existing.score += entityCardWishlistWeight
					existing.reason = "wishlist"
				} else {
					byRef[ref] = &entityCardCandidate{
						entityRef: ref,
						score:     entityCardWishlistWeight,
						reason:    "wishlist",
					}
				}
			}
		}
	}
	if len(byRef) == 0 {
		return nil, nil
	}

	candidates := make([]*entityCardCandidate, 0, len(byRef))
	for _, candidate := range byRef {
		candidates = append(candidates, candidate)
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].score != candidates[j].score {
			return candidates[i].score > candidates[j].score
		}
		return candidates[i].entityRef < candidates[j].entityRef
	})
	refs := make([]string, 0, len(candidates))
	for _, candidate := range candidates {
		refs = append(refs, candidate.entityRef)
		if len(refs) >= limit*3 {
			break
		}
	}

	// 展示装配：只有数据工程档案存在且带主页正文（hasPage）的实体才可成卡。
	entityCursor, err := p.entityColl.Find(
		ctx,
		bson.M{"entityRef": bson.M{"$in": refs}, "hasPage": true},
		options.Find().SetProjection(bson.M{
			"entityRef": 1,
			"label":     1,
			"name":      1,
			"tagRefs":   1,
		}),
	)
	if err != nil {
		return nil, err
	}
	defer entityCursor.Close(ctx)
	var entityDocs []struct {
		EntityRef string   `bson:"entityRef"`
		Label     string   `bson:"label"`
		Name      string   `bson:"name"`
		TagRefs   []string `bson:"tagRefs"`
	}
	if err := entityCursor.All(ctx, &entityDocs); err != nil {
		return nil, err
	}
	docByRef := make(map[string]int, len(entityDocs))
	for i := range entityDocs {
		docByRef[entityDocs[i].EntityRef] = i
	}
	homepageByRef := p.resolveHomepageIDs(ctx, refs)

	cards := make([]feedapp.ObjectCardView, 0, limit)
	for _, candidate := range candidates {
		if len(cards) >= limit {
			break
		}
		idx, ok := docByRef[candidate.entityRef]
		if !ok {
			continue
		}
		homepageID := homepageByRef[candidate.entityRef]
		if homepageID == "" {
			// 无 canonical Homepage 解析的实体不成卡（fail-closed：卡必可点）。
			continue
		}
		doc := entityDocs[idx]
		title := strings.TrimSpace(doc.Label)
		if title == "" {
			title = strings.TrimSpace(doc.Name)
		}
		if title == "" {
			continue
		}
		cards = append(cards, feedapp.ObjectCardView{
			ObjectKind: EntityCardObjectKind,
			// objectId 是可路由的 homepageId（与交集 homepage 跳转同口径），
			// 端侧按 homepageDetail 路由直达对象页。
			ObjectID:   homepageID,
			Title:      title,
			TagRefs:    append([]string(nil), doc.TagRefs...),
			ReasonText: candidate.reason,
			RecallPath: EntityCardRecallPath,
		})
	}
	return cards, nil
}

// resolveHomepageIDs 从 posts 的 entityMentions（实体投影已解析 canonical
// Homepage）反查 entityRef → homepageId：任一 published post 上该实体的
// mention.homepageId 即可路由目标。零新增映射表；canonicalEntityId↔homepageId
// 统一映射物化归 W10 关系投影轨，届时切换消费。
func (p *MongoEntityCardProvider) resolveHomepageIDs(
	ctx context.Context,
	refs []string,
) map[string]string {
	out := make(map[string]string, len(refs))
	if p.postColl == nil || len(refs) == 0 {
		return out
	}
	cursor, err := p.postColl.Find(
		ctx,
		bson.M{
			"entityMentions.subjectId": bson.M{"$in": refs},
			"status":                   "published",
		},
		options.Find().
			SetProjection(bson.M{"entityMentions": 1}).
			SetLimit(entityCardScanLimit),
	)
	if err != nil {
		return out
	}
	defer cursor.Close(ctx)
	var docs []struct {
		EntityMentions []struct {
			SubjectID  string `bson:"subjectId"`
			HomepageID string `bson:"homepageId"`
		} `bson:"entityMentions"`
	}
	if err := cursor.All(ctx, &docs); err != nil {
		return out
	}
	wanted := make(map[string]bool, len(refs))
	for _, ref := range refs {
		wanted[ref] = true
	}
	for _, doc := range docs {
		for _, mention := range doc.EntityMentions {
			subject := strings.TrimSpace(mention.SubjectID)
			homepage := strings.TrimSpace(mention.HomepageID)
			if subject == "" || homepage == "" || !wanted[subject] {
				continue
			}
			if _, ok := out[subject]; !ok {
				out[subject] = homepage
			}
		}
	}
	return out
}

var _ feedapp.ObjectCardProvider = (*MongoEntityCardProvider)(nil)

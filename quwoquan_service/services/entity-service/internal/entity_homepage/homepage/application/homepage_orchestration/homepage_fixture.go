package application

import (
	"encoding/json"
	"time"

	"quwoquan_service/runtime/contractfixture"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type entityFixtureScenarioPack struct {
	SeedSets struct {
		EntityHomepageCore struct {
			Homepages []entityFixtureHomepageSeed `json:"homepages"`
		} `json:"entity_homepage_core"`
	} `json:"seedSets"`
}

type entityFixtureHomepageSeed struct {
	HomepageID        string                          `json:"homepageId"`
	HomepageType      string                          `json:"homepageType"`
	CanonicalEntityID string                          `json:"canonicalEntityId"`
	Title             string                          `json:"title"`
	Subtitle          string                          `json:"subtitle"`
	City              string                          `json:"city"`
	Address           string                          `json:"address"`
	Status            string                          `json:"status"`
	CoverURL          string                          `json:"coverUrl"`
	OwnerID           string                          `json:"ownerId"`
	CategoryTags      []string                        `json:"categoryTags"`
	Geo               *entityFixtureGeo               `json:"geo"`
	AverageRating     *float64                        `json:"averageRating"`
	RatingCount       int                             `json:"ratingCount"`
	ReviewSummary     *homepagemodel.ReviewSummary    `json:"reviewSummary"`
	ContentPreview    []homepagemodel.ContentPreview  `json:"contentPreview"`
	QuestionPreview   []homepagemodel.QuestionPreview `json:"questionPreview"`
	RelatedGroups     []homepagemodel.RelatedGroup    `json:"relatedGroups"`
	RelationEdges     []json.RawMessage               `json:"relationEdges"`
	AssistantContext  json.RawMessage                 `json:"assistantContext"`
	Introduction      *entityFixtureIntroduction      `json:"introduction"`
}

type entityFixtureGeo struct {
	Lat float64 `json:"lat"`
	Lng float64 `json:"lng"`
}

type entityFixtureIntroduction struct {
	CoverURL string `json:"coverUrl"`
}

// LoadHomepageFixtureSnapshots 只供 alpha composition 与 local_contract 显式
// 注入 MemoryHomepageStore；production composition 不调用本函数。
func LoadHomepageFixtureSnapshots() ([]homepagemodel.Snapshot, error) {
	pack, err := contractfixture.LoadRepositoryJSON[entityFixtureScenarioPack](
		"quwoquan_service/services/entity-service/tests/support/contract_fixtures/scenarios/entity_scenarios.json",
	)
	if err != nil {
		return nil, err
	}
	now := time.Now().UTC()
	createdAt := now.Add(-6 * 24 * time.Hour)
	updatedAt := now.Add(-2 * time.Hour)
	publishedAt := now.Add(-72 * time.Hour)
	snapshots := make([]homepagemodel.Snapshot, 0, len(pack.SeedSets.EntityHomepageCore.Homepages))
	for _, fixture := range pack.SeedSets.EntityHomepageCore.Homepages {
		if fixture.HomepageID == "" || fixture.Title == "" ||
			!homepagemodel.ValidHomepageType(fixture.HomepageType) {
			continue
		}
		canonical := fixture.CanonicalEntityID
		if canonical == "" {
			canonical = homepagemodel.CanonicalEntityID(fixture.HomepageType, fixture.Title)
		}
		status := homepagemodel.Status(fixture.Status)
		if status == "" {
			status = homepagemodel.StatusPublished
		}
		coverURL := fixture.CoverURL
		if coverURL == "" && fixture.Introduction != nil {
			coverURL = fixture.Introduction.CoverURL
		}
		snapshot := homepagemodel.Snapshot{
			ID:                 fixture.HomepageID,
			Version:            1,
			Title:              fixture.Title,
			Subtitle:           fixture.Subtitle,
			HomepageType:       fixture.HomepageType,
			CanonicalEntityID:  canonical,
			LookupAliases:      []string{fixture.HomepageID, canonical, fixture.Title},
			ObjectPageTemplate: objectPageTemplate(fixture.HomepageType, ""),
			Status:             status,
			SourceType:         "official_seed",
			ClaimStatus:        "unclaimed",
			CategoryTags:       fixture.CategoryTags,
			CoverURL:           coverURL,
			Address:            fixture.Address,
			City:               fixture.City,
			OwnerUserID:        fixture.OwnerID,
			CreatedAt:          createdAt,
			UpdatedAt:          updatedAt,
		}
		if fixture.Geo != nil {
			snapshot.Location = &homepagemodel.GeoPoint{
				Latitude: fixture.Geo.Lat, Longitude: fixture.Geo.Lng,
			}
		}
		if status == homepagemodel.StatusPublished {
			published := publishedAt
			snapshot.PublishedAt = &published
		}
		aggregate, restoreErr := homepagemodel.Restore(snapshot)
		if restoreErr != nil {
			return nil, restoreErr
		}
		snapshots = append(snapshots, aggregate.Snapshot())
	}
	return snapshots, nil
}

// LoadHomepageFixtureDetailProjections 与 LoadHomepageFixtureSnapshots 分开
// 返回读投影，确保 fixture 也不会把跨对象字段塞回 Homepage 写聚合。
func LoadHomepageFixtureDetailProjections() ([]homepageports.DetailProjection, error) {
	pack, err := contractfixture.LoadRepositoryJSON[entityFixtureScenarioPack](
		"quwoquan_service/services/entity-service/tests/support/contract_fixtures/scenarios/entity_scenarios.json",
	)
	if err != nil {
		return nil, err
	}
	updatedAt := time.Now().UTC().Add(-2 * time.Hour)
	projections := make([]homepageports.DetailProjection, 0, len(pack.SeedSets.EntityHomepageCore.Homepages))
	for _, fixture := range pack.SeedSets.EntityHomepageCore.Homepages {
		// 与写聚合 fixture 使用同一准入条件；否则已被聚合模型拒绝的旧类型
		// 仍会生成孤儿读投影，并在 SeedDetailProjection 时伪造父对象。
		if fixture.HomepageID == "" || fixture.Title == "" ||
			!homepagemodel.ValidHomepageType(fixture.HomepageType) {
			continue
		}
		projections = append(projections, homepageports.DetailProjection{
			HomepageID:       fixture.HomepageID,
			AverageRating:    fixture.AverageRating,
			RatingCount:      fixture.RatingCount,
			ReviewSummary:    fixture.ReviewSummary,
			ContentPreview:   fixture.ContentPreview,
			QuestionPreview:  fixture.QuestionPreview,
			RelatedGroups:    fixture.RelatedGroups,
			RelationEdges:    fixture.RelationEdges,
			AssistantContext: fixture.AssistantContext,
			UpdatedAt:        updatedAt,
		})
	}
	return projections, nil
}

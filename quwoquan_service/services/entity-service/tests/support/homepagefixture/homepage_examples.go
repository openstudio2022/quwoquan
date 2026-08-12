// Package homepagefixture builds entity Homepage test state from object-level
// contract examples. Production packages and environment composition must not
// import this package.
package homepagefixture

import (
	"context"
	"encoding/json"
	"time"

	"quwoquan_service/runtime/contractfixture"
	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

const examplesPath = "quwoquan_service/services/entity-service/tests/support/contract_examples/entity_homepage_examples.json"

type examplePack struct {
	Examples struct {
		EntityHomepageCore struct {
			Homepages []homepageExample `json:"homepages"`
		} `json:"entity_homepage_core"`
	} `json:"examples"`
}

type homepageExample struct {
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
	Geo               *geoExample                     `json:"geo"`
	AverageRating     *float64                        `json:"averageRating"`
	RatingCount       int                             `json:"ratingCount"`
	ReviewSummary     *homepagemodel.ReviewSummary    `json:"reviewSummary"`
	ContentPreview    []homepagemodel.ContentPreview  `json:"contentPreview"`
	QuestionPreview   []homepagemodel.QuestionPreview `json:"questionPreview"`
	RelatedGroups     []homepagemodel.RelatedGroup    `json:"relatedGroups"`
	RelationEdges     []json.RawMessage               `json:"relationEdges"`
	AssistantContext  json.RawMessage                 `json:"assistantContext"`
	Introduction      *introductionExample            `json:"introduction"`
}

type geoExample struct {
	Lat float64 `json:"lat"`
	Lng float64 `json:"lng"`
}

type introductionExample struct {
	CoverURL string `json:"coverUrl"`
}

func loadExamples() ([]homepageExample, error) {
	pack, err := contractfixture.LoadRepositoryJSON[examplePack](examplesPath)
	if err != nil {
		return nil, err
	}
	return pack.Examples.EntityHomepageCore.Homepages, nil
}

// LoadHomepageExampleSnapshots returns deterministic object examples for
// local_contract and isolated api_integration stores.
func LoadHomepageExampleSnapshots() ([]homepagemodel.Snapshot, error) {
	examples, err := loadExamples()
	if err != nil {
		return nil, err
	}
	now := time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC)
	createdAt := now.Add(-6 * 24 * time.Hour)
	updatedAt := now.Add(-2 * time.Hour)
	publishedAt := now.Add(-72 * time.Hour)
	snapshots := make([]homepagemodel.Snapshot, 0, len(examples))
	for _, example := range examples {
		if example.HomepageID == "" || example.Title == "" ||
			!homepagemodel.ValidHomepageType(example.HomepageType) {
			continue
		}
		canonical := example.CanonicalEntityID
		if canonical == "" {
			canonical = homepagemodel.CanonicalEntityID(example.HomepageType, example.Title)
		}
		status := homepagemodel.Status(example.Status)
		if status == "" {
			status = homepagemodel.StatusPublished
		}
		coverURL := example.CoverURL
		if coverURL == "" && example.Introduction != nil {
			coverURL = example.Introduction.CoverURL
		}
		snapshot := homepagemodel.Snapshot{
			ID: example.HomepageID, Version: 1, Title: example.Title,
			Subtitle: example.Subtitle, HomepageType: example.HomepageType,
			CanonicalEntityID:  canonical,
			LookupAliases:      []string{example.HomepageID, canonical, example.Title},
			ObjectPageTemplate: homepagemodel.ObjectPageTemplate(example.HomepageType, ""),
			Status:             status, SourceType: "contract_example", ClaimStatus: "unclaimed",
			CategoryTags: example.CategoryTags, CoverURL: coverURL,
			Address: example.Address, City: example.City, OwnerUserID: example.OwnerID,
			CreatedAt: createdAt, UpdatedAt: updatedAt,
		}
		if example.Geo != nil {
			snapshot.Location = &homepagemodel.GeoPoint{
				Latitude: example.Geo.Lat, Longitude: example.Geo.Lng,
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

// LoadHomepageExampleDetailProjections keeps read-only cross-object fields
// outside the Homepage write aggregate.
func LoadHomepageExampleDetailProjections() ([]homepageports.DetailProjection, error) {
	examples, err := loadExamples()
	if err != nil {
		return nil, err
	}
	updatedAt := time.Date(2026, 7, 31, 22, 0, 0, 0, time.UTC)
	projections := make([]homepageports.DetailProjection, 0, len(examples))
	for _, example := range examples {
		if example.HomepageID == "" || example.Title == "" ||
			!homepagemodel.ValidHomepageType(example.HomepageType) {
			continue
		}
		projections = append(projections, homepageports.DetailProjection{
			HomepageID: example.HomepageID, AverageRating: example.AverageRating,
			RatingCount: example.RatingCount, ReviewSummary: example.ReviewSummary,
			ContentPreview: example.ContentPreview, QuestionPreview: example.QuestionPreview,
			RelatedGroups: example.RelatedGroups, RelationEdges: example.RelationEdges,
			AssistantContext: example.AssistantContext, UpdatedAt: updatedAt,
		})
	}
	return projections, nil
}

func NewFixtureHomepageService() *homepageapp.HomepageService {
	return NewFixtureHomepageServiceWithOptions()
}

func NewFixtureHomepageServiceWithOptions(
	options ...homepageapp.HomepageServiceOption,
) *homepageapp.HomepageService {
	seeds, err := LoadHomepageExampleSnapshots()
	if err != nil {
		panic(err)
	}
	store, err := homepagepersistence.NewMemoryHomepageStore(seeds...)
	if err != nil {
		panic(err)
	}
	projections, err := LoadHomepageExampleDetailProjections()
	if err != nil {
		panic(err)
	}
	for _, projection := range projections {
		if err := store.SeedDetailProjection(projection); err != nil {
			panic(err)
		}
	}
	return homepageapp.NewHomepageServiceWithStore(context.Background(), store, options...)
}

func NewEmptyHomepageService() (*homepageapp.HomepageService, *homepagepersistence.MemoryHomepageStore) {
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		panic(err)
	}
	return homepageapp.NewHomepageServiceWithStore(context.Background(), store), store
}

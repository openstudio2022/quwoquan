// Package testsupport assembles entity-service local contract fixtures.
// Production composition must never import this package.
package testsupport

import (
	"context"

	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	homepagepersistence "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/persistence"
)

func NewFixtureHomepageService() *application.HomepageService {
	return NewFixtureHomepageServiceWithOptions()
}

func NewFixtureHomepageServiceWithOptions(
	options ...application.HomepageServiceOption,
) *application.HomepageService {
	seeds, err := application.LoadHomepageFixtureSnapshots()
	if err != nil {
		panic(err)
	}
	store, err := homepagepersistence.NewMemoryHomepageStore(seeds...)
	if err != nil {
		panic(err)
	}
	projections, err := application.LoadHomepageFixtureDetailProjections()
	if err != nil {
		panic(err)
	}
	for _, projection := range projections {
		if err := store.SeedDetailProjection(projection); err != nil {
			panic(err)
		}
	}
	return application.NewHomepageServiceWithStore(
		context.Background(),
		store,
		options...,
	)
}

func NewEmptyHomepageService() (*application.HomepageService, *homepagepersistence.MemoryHomepageStore) {
	store, err := homepagepersistence.NewMemoryHomepageStore()
	if err != nil {
		panic(err)
	}
	return application.NewHomepageServiceWithStore(context.Background(), store), store
}

package bootstrap

import (
	"context"
	"net/http"

	"go.mongodb.org/mongo-driver/v2/mongo"

	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	planhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/adapters/inbound/http"
	planapp "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/application"
	planexternal "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/infrastructure/external"
	planpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/infrastructure/persistence"
)

func registerGatheringPlanRuntime(
	ctx context.Context,
	mux *http.ServeMux,
	database *mongo.Database,
	gatheringStore gatheringports.AggregateStore,
) error {
	store := planpersistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		return err
	}
	reader := planpersistence.NewMongoGatheringPlanReader(database)
	ownerAuthority := gatheringapp.NewGatheringPlanAuthorityReader(gatheringStore)
	authority := planexternal.NewGatheringAuthorityReader(ownerAuthority)
	planhttp.NewHandler(
		planapp.NewGatheringPlanCommandFacet(store, authority),
		planapp.NewGatheringPlanQueryFacet(reader, authority),
		mapGatheringPlanError,
	).Register(mux)
	return nil
}

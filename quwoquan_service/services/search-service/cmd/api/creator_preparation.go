package bootstrap

import (
	"context"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"net/http"
	"quwoquan_service/runtime/auth"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	indexapp "quwoquan_service/services/search-service/internal/search/search_index_view/application"
	fencehttp "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/contentfence"
	provider "quwoquan_service/services/search-service/internal/search/search_index_view/infrastructure/creatorprojection"
	preparationhttp "quwoquan_service/services/search-service/internal/search/search_release_preparation/adapters/inbound/http"
	preparation "quwoquan_service/services/search-service/internal/search/search_release_preparation/application"
	persistence "quwoquan_service/services/search-service/internal/search/search_release_preparation/infrastructure/persistence"
	"time"
)

type fencePreparationProof struct {
	service *preparation.Service
	schema  string
}

func (p fencePreparationProof) VerifyFenceCandidate(ctx context.Context, b rt.ReleaseCandidateBinding) (string, error) {
	return p.service.ReconcileRelease(ctx, b, p.schema)
}

// RegisterCreatorPreparation只接受部署authority已验证的generation，不从请求或CONFIG_VERSION猜测。
// 正式Bootstrap接入须先补齐配置/部署binding的authoring；本函数无隐式开关或fallback。
func RegisterCreatorPreparation(ctx context.Context, mux *http.ServeMux, db *mongo.Database, writer, reader *es.Client, environment, generation, namespace, contentURL string, credentials auth.ServiceAuthorizationProvider, postHandlers ...*indexapp.ContentPostHandler) (*indexapp.CreatorQueryFence, error) {
	if err := reader.VerifyPhysicalNamespace(ctx, namespace); err != nil {
		return nil, err
	}
	if err := writer.VerifyPhysicalNamespace(ctx, namespace); err != nil {
		return nil, err
	}
	store := persistence.NewMongoStore(db)
	if err := store.EnsureIndexes(ctx); err != nil {
		return nil, err
	}
	projector := indexapp.NewReleaseCandidateProjector(provider.NewProvider(writer, reader, namespace))
	service, err := preparation.NewService(store, projector, environment, generation, time.Now)
	if err != nil {
		return nil, err
	}
	fenceReader, err := fencehttp.NewReader(contentURL, environment, credentials)
	if err != nil {
		return nil, err
	}
	fence, err := indexapp.NewCreatorQueryFence(fenceReader, environment, generation, reader.SchemaGeneration())
	if err != nil {
		return nil, err
	}
	if len(postHandlers) > 0 {
		receipts := fencehttp.NewReconciliationStore(db)
		if err := receipts.EnsureIndexes(ctx); err != nil {
			return nil, err
		}
		commits, err := fencehttp.NewCommitReader(contentURL, credentials)
		if err != nil {
			return nil, err
		}
		reconciler, err := indexapp.NewContentFenceReconciler(receipts, commits, fenceReader, fencePreparationProof{service, reader.SchemaGeneration()}, environment)
		if err != nil {
			return nil, err
		}
		if err = postHandlers[0].BindFenceReconciler(reconciler); err != nil {
			return nil, err
		}
	}
	preparationhttp.NewHandler(service).Register(mux)
	return fence, nil
}

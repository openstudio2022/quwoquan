package bootstrap

import (
	"context"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"net/http"
	inbound "quwoquan_service/services/content-service/internal/content/post_collection/adapters/inbound/graphql"
	app "quwoquan_service/services/content-service/internal/content/post_collection/application"
	domain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	store "quwoquan_service/services/content-service/internal/content/post_collection/infrastructure/persistence"
	"time"
)

// 仅暴露模块组合所需的 application typed ports，不开放对象 persistence。
type CollectionMember = app.Member
type CollectionVisibility = domain.Visibility
type CollectionSave = domain.Save
type CollectionResult = app.Result
type CollectionPostReader interface {
	ReadVisible(context.Context, string, string) (CollectionMember, bool, error)
}
type CollectionCoverReader interface {
	CanUseCover(context.Context, string, string, CollectionVisibility) (bool, error)
}
type CollectionCommands interface {
	Save(context.Context, string, CollectionSave) (CollectionResult, error)
}

func NewCollectionQueryHTTP(db *mongo.Database, posts CollectionPostReader, covers CollectionCoverReader, authority inbound.Authority, graph string) (http.Handler, CollectionCommands, error) {
	persistence, err := store.New(db)
	if err != nil {
		return nil, nil, err
	}
	service, err := app.New(persistence, posts, covers, time.Now)
	if err != nil {
		return nil, nil, err
	}
	return inbound.Handler{Service: service, Authority: authority, GraphHash: graph}, service, nil
}

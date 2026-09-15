package bootstrap

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"net/http"
	"quwoquan_service/generated/operationsecurity"
	auth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/servicekit"
	postapp "quwoquan_service/services/content-service/internal/content/post/application"
	collectiongraphql "quwoquan_service/services/content-service/internal/content/post_collection/adapters/inbound/graphql"
	collectionhttp "quwoquan_service/services/content-service/internal/content/post_collection/adapters/inbound/http"
	collectionapp "quwoquan_service/services/content-service/internal/content/post_collection/application"
	collectiondomain "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	collectionstore "quwoquan_service/services/content-service/internal/content/post_collection/infrastructure/persistence"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	"time"
)

// 多对象组合只在 cmd；封面不能通过合集公开性放宽资产原有权限。
type collectionCoverReader struct{ media mediaapp.MediaAssetQueryFacet }

func (r collectionCoverReader) CanUseCover(ctx context.Context, id, viewer string, visibility collectiondomain.Visibility) (bool, error) {
	if r.media == nil {
		return false, errors.New("MediaAsset query unavailable")
	}
	var slice mediaapp.MediaAssetSlice
	var err error
	if visibility == collectiondomain.Public {
		slice, err = r.media.GetPublicMediaAsset(ctx, mediaapp.GetPublicMediaAssetQuery{AssetID: id})
	} else {
		if viewer == "" {
			return false, nil
		}
		slice, err = r.media.GetMediaAsset(ctx, mediaapp.GetMediaAssetQuery{AssetID: id, OwnerID: viewer})
	}
	if err != nil {
		var appErr *rterr.AppError
		if errors.As(err, &appErr) && (appErr.HTTPStatus == 404 || appErr.HTTPStatus == 403) {
			return false, nil
		}
		return false, err
	}
	return slice.AssetID == id && slice.MediaType == "image" && slice.ProcessingStatus == mediamodel.ProcessingStatusReady && slice.DeliveryURL != "", nil
}
func buildPostCollectionHandler(db *mongo.Database, posts *postapp.PostQueryFacade, media mediaapp.MediaAssetQueryFacet, next http.Handler) (http.Handler, *collectionapp.Service, error) {
	store, err := collectionstore.New(db)
	if err != nil {
		return nil, nil, err
	}
	service, err := collectionapp.New(store, collectionapp.CanonicalPostReader{Query: posts}, collectionCoverReader{media: media}, time.Now)
	if err != nil {
		return nil, nil, err
	}
	mux := http.NewServeMux()
	collectionhttp.Handler{Service: service}.Register(mux)
	mux.Handle("/", next)
	return mux, service, nil
}
func collectionAuthorityVerifier(asm *servicekit.Assembly, cfg *config) (*auth.CollectionQueryAuthorityClient, error) {
	var issuePath, verifyPath string
	for _, d := range operationsecurity.ForDomain("user") {
		switch d.CanonicalOperationID {
		case "user.user_account.IssueCollectionQueryGrant":
			issuePath = d.PathTemplate
		case "user.user_account.VerifyCollectionQueryGrant":
			verifyPath = d.PathTemplate
		}
	}
	credentials, err := asm.Auth.ServiceCredentials("user.collection_query.verify")
	if err != nil {
		return nil, err
	}
	return auth.NewCollectionQueryAuthorityClient(cfg.UserAccountSecurityAuthority.BaseURL, issuePath, verifyPath, credentials, &http.Client{Timeout: 800 * time.Millisecond})
}
func wrapCollectionGraphQL(service *collectionapp.Service, verifier collectiongraphql.Authority, hash string, next http.Handler) http.Handler {
	return collectiongraphql.Handler{Service: service, Authority: verifier, GraphHash: hash, Next: next}
}

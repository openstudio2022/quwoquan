package bootstrap

import (
	"context"
	"errors"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"quwoquan_service/runtime/auth"
	indexpersistence "quwoquan_service/services/tag-service/internal/tag/object_tag_index_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/infrastructure/persistence"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/contentfence"
	"time"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/infrastructure/taxonomyreleasestore"
)

// newContentFencedTagService 是生产 bootstrap 与真实 HTTP 回归共用的组合入口。
func newContentFencedTagService(db *mongo.Database, environment, endpoint string, timeout time.Duration, credentials auth.ServiceAuthorizationProvider) (*application.TagService, *contentActiveReleaseReader, error) {
	fence, err := contentfence.NewHTTPReader(endpoint, environment, timeout, credentials)
	if err != nil {
		return nil, nil, err
	}
	active := &contentActiveReleaseReader{fence: fence, candidates: taxonomyreleasestore.NewContentCandidateStore(db)}
	service := application.NewTagService(persistence.NewMongoTagNodeStore(db.Collection("tag_nodes")), indexpersistence.NewMongoObjectTagIndexStore(db.Collection("object_tag_index")), active)
	return service, active, nil
}

type verifiedCandidateReader interface {
	ReadVerifiedContentCandidate(context.Context, string, string, string, string) (taxonomyreleasestore.ContentCandidate, bool, error)
}

// contentActiveReleaseReader 在组合根连接 Content 只读 port 与 Tag owning candidate；所有查询只 pin 一次 fence。
type contentActiveReleaseReader struct {
	fence      ports.ContentFenceReader
	candidates verifiedCandidateReader
}

func (r *contentActiveReleaseReader) ActiveReleaseID(ctx context.Context) (string, bool, error) {
	fence, err := r.fence.ReadActiveContentFence(ctx)
	if err != nil {
		return "", false, err
	}
	if !fence.Found {
		return "", false, nil
	}
	candidate, found, err := r.candidates.ReadVerifiedContentCandidate(ctx, fence.Environment, fence.SourceOwner, fence.ReleaseID, fence.ManifestDigest)
	if err != nil {
		return "", false, err
	}
	if !found || candidate.Status != "verified" || candidate.Environment != fence.Environment || candidate.SourceOwner != fence.SourceOwner || candidate.ReleaseID != fence.ReleaseID || candidate.ManifestDigest != fence.ManifestDigest {
		return "", false, errors.New("Content active fence has no matching verified Tag candidate")
	}
	return candidate.ReleaseID, true, nil
}

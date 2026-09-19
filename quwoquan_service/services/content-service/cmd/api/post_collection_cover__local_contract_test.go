package bootstrap

// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/ordered-post-collection/spec.md#gwt-002.t1
import (
	"context"
	"errors"
	collection "quwoquan_service/services/content-service/internal/content/post_collection/domain"
	media "quwoquan_service/services/content-service/internal/media/media_asset/application"
	model "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
	"testing"
)

type collectionMediaReader struct {
	media.MediaAssetQueryFacet
	slice  media.MediaAssetSlice
	err    error
	public bool
	owner  string
}

func (r *collectionMediaReader) GetPublicMediaAsset(context.Context, media.GetPublicMediaAssetQuery) (media.MediaAssetSlice, error) {
	r.public = true
	return r.slice, r.err
}
func (r *collectionMediaReader) GetMediaAsset(_ context.Context, q media.GetMediaAssetQuery) (media.MediaAssetSlice, error) {
	r.owner = q.OwnerID
	return r.slice, r.err
}
func TestCollectionCoverHonorsPublicAndOwnerReaders(t *testing.T) {
	ctx := context.Background()
	up := &collectionMediaReader{slice: media.MediaAssetSlice{AssetID: "cover", MediaType: "image", ProcessingStatus: model.ProcessingStatusReady, DeliveryURL: "https://media.invalid/cover"}}
	reader := collectionCoverReader{media: up}
	if ok, err := reader.CanUseCover(ctx, "cover", "viewer", collection.Public); err != nil || !ok || !up.public {
		t.Fatal(ok, err)
	}
	if ok, err := reader.CanUseCover(ctx, "cover", "owner", collection.Private); err != nil || !ok || up.owner != "owner" {
		t.Fatal(ok, err)
	}
	up.err = errors.New("media unavailable")
	if ok, err := reader.CanUseCover(ctx, "cover", "owner", collection.Public); err == nil || ok {
		t.Fatal("dependency failure was accepted")
	}
	up.err = nil
	up.slice.ProcessingStatus = model.ProcessingStatus("processing")
	if ok, err := reader.CanUseCover(ctx, "cover", "owner", collection.Public); err != nil || ok {
		t.Fatal("unready cover was accepted")
	}
}

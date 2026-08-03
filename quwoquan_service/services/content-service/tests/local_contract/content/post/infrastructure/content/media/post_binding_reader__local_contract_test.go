package media_test

import (
	"context"
	. "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media"
	"testing"

	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

func TestPostBindingReaderPublishesNormalizedImageBytes(t *testing.T) {
	const (
		assetID       = "mas_image_001"
		originalKey   = "media/private/original"
		normalizedKey = "media/processed/image/mas_image_001/v2/source.jpg"
		publicKey     = "media/image/s/asset/mas_image_001/v2/source.jpg"
	)
	assets := &postBindingAssetReader{assets: map[string]mediaapp.MediaAssetSlice{
		assetID: {
			AssetID:                  assetID,
			OwnerID:                  "persona-1",
			MediaType:                "image",
			MimeType:                 "image/png",
			Version:                  2,
			ObjectKey:                originalKey,
			ProcessingStatus:         mediamodel.ProcessingStatusReady,
			ImageNormalizedObjectKey: normalizedKey,
			ImagePublicSliceKey:      publicKey,
		},
	}}
	publisher := &recordingPublicSlicePublisher{}
	reader := NewPostBindingReader(assets, publisher)

	bindings, err := reader.FindMediaAssetsForBinding(
		context.Background(),
		[]string{assetID},
	)
	if err != nil {
		t.Fatalf("find bindings: %v", err)
	}
	if got := bindings[assetID].PublicSliceKey; got != publicKey {
		t.Fatalf("public slice key=%q want=%q", got, publicKey)
	}
	if err := reader.MaterializePublicSlices(
		context.Background(),
		[]string{assetID},
	); err != nil {
		t.Fatalf("materialize: %v", err)
	}
	if publisher.sourceKey != normalizedKey || publisher.publicKey != publicKey {
		t.Fatalf(
			"publish normalized=%q public=%q; original source must not be exposed",
			publisher.sourceKey,
			publisher.publicKey,
		)
	}
}

func TestPostBindingReaderRejectsReadyImageWithoutNormalizedSource(t *testing.T) {
	const assetID = "mas_image_invalid"
	assets := &postBindingAssetReader{assets: map[string]mediaapp.MediaAssetSlice{
		assetID: {
			AssetID:             assetID,
			OwnerID:             "persona-1",
			MediaType:           "image",
			MimeType:            "image/jpeg",
			Version:             1,
			ObjectKey:           "media/private/original",
			ProcessingStatus:    mediamodel.ProcessingStatusReady,
			ImagePublicSliceKey: "media/image/s/asset/mas_image_invalid/v1/source.jpg",
		},
	}}
	publisher := &recordingPublicSlicePublisher{}
	reader := NewPostBindingReader(assets, publisher)

	if err := reader.MaterializePublicSlices(
		context.Background(),
		[]string{assetID},
	); err == nil {
		t.Fatal("expected missing normalized source to be rejected")
	}
	if publisher.calls != 0 {
		t.Fatalf("publisher called %d times for an invalid ready image", publisher.calls)
	}
}

func TestPostBindingReaderKeepsHLSCMAFPairedWithProgressiveVideo(t *testing.T) {
	const (
		assetID     = "mas_video_hls_001"
		prefix      = "media/video/s/asset/mas_video_hls_001/v4"
		progressive = prefix + "/source.mp4"
		descriptor  = prefix + "/hls/descriptor.json"
		master      = prefix + "/hls/master.m3u8"
	)
	assets := &postBindingAssetReader{assets: map[string]mediaapp.MediaAssetSlice{
		assetID: {
			AssetID:                       assetID,
			OwnerID:                       "persona-1",
			MediaType:                     "video",
			MimeType:                      "video/mp4",
			Version:                       4,
			ProcessingStatus:              mediamodel.ProcessingStatusReady,
			VideoPublicSliceKey:           progressive,
			CoverPublicSliceKey:           prefix + "/cover.jpg",
			HLSCMAFDescriptorVersion:      1,
			HLSCMAFDescriptorSliceKey:     descriptor,
			HLSCMAFMasterManifestSliceKey: master,
			HLSCMAFRenditionCount:         3,
		},
	}}
	reader := NewPostBindingReader(assets, &recordingPublicSlicePublisher{})

	bindings, err := reader.FindMediaAssetsForBinding(
		context.Background(),
		[]string{assetID},
	)
	if err != nil {
		t.Fatalf("find HLS/CMAF video binding: %v", err)
	}
	got := bindings[assetID]
	if got.PublicSliceKey != progressive || got.VideoPublicSliceKey != progressive ||
		got.HLSCMAFDescriptorVersion != 1 ||
		got.HLSCMAFDescriptorSliceKey != descriptor ||
		got.HLSCMAFMasterManifestSliceKey != master ||
		got.HLSCMAFRenditionCount != 3 {
		t.Fatalf("HLS/CMAF binding lost canonical P0/P1 pairing: %+v", got)
	}
}

type postBindingAssetReader struct {
	assets map[string]mediaapp.MediaAssetSlice
}

func (r *postBindingAssetReader) FindMediaAssetsByIDs(
	_ context.Context,
	_ []string,
) (map[string]mediaapp.MediaAssetSlice, error) {
	return r.assets, nil
}

type recordingPublicSlicePublisher struct {
	calls     int
	sourceKey string
	publicKey string
}

func (p *recordingPublicSlicePublisher) PublishPublicSlice(
	_ context.Context,
	sourceKey string,
	publicKey string,
) error {
	p.calls++
	p.sourceKey = sourceKey
	p.publicKey = publicKey
	return nil
}

package post

import (
	"context"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	mediamodel "quwoquan_service/services/content-service/internal/content/post/domain/media/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
)

// DataPorts 显式装配 Post 对象的写端口、具名读取 Slice 与计数投影端口。
type DataPorts struct {
	Aggregate   postports.AggregateStore
	Detail      postports.DetailReader
	Collection  postports.CollectionReader
	Counters    postports.CounterStore
	MediaAssets MediaAssetBindingReader
}

type MediaAssetBindingSlice struct {
	AssetID                       string
	OwnerID                       string
	Ready                         bool
	ProcessingStatus              string
	MediaType                     string
	MimeType                      string
	Version                       int64
	CaptureMetadata               mediamodel.CaptureMetadata
	PublicSliceKey                string
	VerifiedDurationMs            int64
	VideoWidth                    int
	VideoHeight                   int
	VideoPublicSliceKey           string
	CoverPublicSliceKey           string
	PreviewTrackVersion           int
	PreviewTrackManifestSliceKey  string
	HLSCMAFDescriptorVersion      int
	HLSCMAFDescriptorSliceKey     string
	HLSCMAFMasterManifestSliceKey string
	HLSCMAFRenditionCount         int
	CoverStrategy                 string
	ManualCoverAssetID            string
	CoverFrameTimeMs              int64
}

type MediaAssetBindingReader interface {
	FindMediaAssetsForBinding(context.Context, []string) (map[string]MediaAssetBindingSlice, error)
	MaterializePublicSlices(context.Context, []string) error
}

// BindDataPorts 供同一个对象 adapter 同时实现多个细粒度端口时装配使用。
func BindDataPorts(adapter interface {
	postports.AggregateStore
	postports.DetailReader
	postports.CollectionReader
	postports.CounterStore
}) DataPorts {
	return DataPorts{
		Aggregate:  adapter,
		Detail:     adapter,
		Collection: adapter,
		Counters:   adapter,
	}
}

func WithMediaAssetBindingReader(data DataPorts, reader MediaAssetBindingReader) DataPorts {
	data.MediaAssets = reader
	return data
}

// postDataAccess 是应用内部的组合器，不是对外数据 port。
type postDataAccess struct {
	ports DataPorts
}

func (a postDataAccess) FindByID(ctx context.Context, postID string) (*postmodel.Post, bool) {
	return a.ports.Detail.FindByID(ctx, postID)
}

func (a postDataAccess) FindByPublicationIntent(
	ctx context.Context,
	authorID string,
	publishIntentID string,
) (*postmodel.Post, bool) {
	return a.ports.Detail.FindByPublicationIntent(
		ctx,
		authorID,
		publishIntentID,
	)
}

func (a postDataAccess) ListAll(ctx context.Context) ([]postmodel.Post, error) {
	return a.ports.Collection.ListAll(ctx)
}

func (a postDataAccess) ListPublished(ctx context.Context, limit int, cursor string) []postmodel.Post {
	return a.ports.Collection.ListPublished(ctx, limit, cursor)
}

func (a postDataAccess) ListByAuthor(ctx context.Context, authorID string, limit int, cursor string) []postmodel.Post {
	return a.ports.Collection.ListByAuthor(ctx, authorID, limit, cursor)
}

func (a postDataAccess) AdjustCommentCount(ctx context.Context, postID string, delta int64) (int64, bool, error) {
	return a.ports.Counters.AdjustCommentCount(ctx, postID, delta)
}

func (a postDataAccess) SetCommentCount(ctx context.Context, postID string, count int64) (bool, error) {
	return a.ports.Counters.SetCommentCount(ctx, postID, count)
}

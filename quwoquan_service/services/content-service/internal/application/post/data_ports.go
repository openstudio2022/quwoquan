package post

import (
	"context"
	"fmt"
	"time"

	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
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
	AssetID string
	OwnerID string
	Ready   bool
}

type MediaAssetBindingReader interface {
	FindMediaAssetsForBinding(context.Context, []string) (map[string]MediaAssetBindingSlice, error)
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

func (a postDataAccess) Create(ctx context.Context, post *postmodel.Post) error {
	_, err := a.ports.Aggregate.Commit(ctx, postports.Commit{
		Post:             post,
		ExpectedVersion:  0,
		IdempotencyKey:   "create:" + post.ID,
		CommandName:      "CreatePost",
		CommandDigest:    post.ID,
		ReceiptExpiresAt: time.Now().UTC().Add(24 * time.Hour),
	})
	return err
}

func (a postDataAccess) Update(ctx context.Context, postID string, post *postmodel.Post) bool {
	if post == nil {
		return false
	}
	result, err := a.ports.Aggregate.Commit(ctx, postports.Commit{
		Post:             post,
		ExpectedVersion:  post.Version,
		IdempotencyKey:   fmt.Sprintf("update:%s:%d", postID, post.Version),
		CommandName:      "UpdatePost",
		CommandDigest:    fmt.Sprintf("%s:%d", postID, post.Version),
		ReceiptExpiresAt: time.Now().UTC().Add(24 * time.Hour),
	})
	return err == nil && result.Post != nil
}

func (a postDataAccess) FindByID(ctx context.Context, postID string) (*postmodel.Post, bool) {
	return a.ports.Detail.FindByID(ctx, postID)
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

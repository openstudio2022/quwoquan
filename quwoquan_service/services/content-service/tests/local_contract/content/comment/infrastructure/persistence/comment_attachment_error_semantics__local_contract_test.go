// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#req-004
//
// CommentAttachmentReader 声明错误码的负例断言：附件缺失或未就绪时必须
// 经 generated AppError 工厂发射 comment_attachment_not_ready，以字面
// wire code 锁定端云契约。
package persistence_test

import (
	"context"
	"errors"
	"testing"
	"time"

	rterr "quwoquan_service/runtime/errors"
	commentpersistence "quwoquan_service/services/content-service/internal/content/comment/infrastructure/persistence"
	mediaapp "quwoquan_service/services/content-service/internal/media/media_asset/application"
	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

type fixedMediaAssetReader struct {
	assets map[string]mediaapp.MediaAssetSlice
}

func (r fixedMediaAssetReader) FindMediaAssetsByIDs(
	context.Context,
	[]string,
) (map[string]mediaapp.MediaAssetSlice, error) {
	return r.assets, nil
}

type noopMediaObjectGateway struct{}

func (noopMediaObjectGateway) PublishPublicSlice(context.Context, string, string) error {
	return nil
}

func (noopMediaObjectGateway) DeliveryURL(context.Context, string) (string, error) {
	return "https://media-fixture.invalid/object", nil
}

func (noopMediaObjectGateway) DeliveryURLUntil(
	context.Context,
	string,
	time.Time,
) (string, error) {
	return "https://media-fixture.invalid/object", nil
}

func requireAttachmentAppErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rterr.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func TestValidateCommentAttachmentsMissingAssetEmitsCommentAttachmentNotReady(t *testing.T) {
	reader := commentpersistence.NewCommentAttachmentReader(
		fixedMediaAssetReader{assets: map[string]mediaapp.MediaAssetSlice{}},
		noopMediaObjectGateway{},
	)
	err := reader.ValidateCommentAttachments(
		context.Background(),
		"persona-author",
		[]string{"media-absent"},
	)
	requireAttachmentAppErrorCode(t, err, "CONTENT.USER.comment_attachment_not_ready")
}

func TestValidateCommentAttachmentsProcessingAssetEmitsCommentAttachmentNotReady(t *testing.T) {
	reader := commentpersistence.NewCommentAttachmentReader(
		fixedMediaAssetReader{assets: map[string]mediaapp.MediaAssetSlice{
			"media-processing": {
				AssetID:          "media-processing",
				OwnerID:          "persona-author",
				ProcessingStatus: mediamodel.ProcessingStatusProcessing,
			},
		}},
		noopMediaObjectGateway{},
	)
	err := reader.ValidateCommentAttachments(
		context.Background(),
		"persona-author",
		[]string{"media-processing"},
	)
	requireAttachmentAppErrorCode(t, err, "CONTENT.USER.comment_attachment_not_ready")
}

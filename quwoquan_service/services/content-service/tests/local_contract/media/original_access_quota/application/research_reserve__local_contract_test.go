// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// DEC-031 grant 研究分流：research principal 只允许 purpose=view，可为当前
// active research release 闭包内 ready 的 avatar|image|video 资产签发短签；
// release membership 缺失、无 active research release 或 reader 未接线均
// fail closed。普通会话保持 ready image + Post 可见性 + view|save，不受影响。
package application

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	quotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

type fakeQuotaStore struct{}

func (fakeQuotaStore) Reserve(
	_ context.Context,
	reservation quotamodel.Reservation,
	_ quotamodel.Policy,
) (quotaports.ReserveResult, error) {
	return quotaports.ReserveResult{Reservation: reservation}, nil
}

type recordingAuditAppender struct {
	decisions []quotaports.AuditDecision
}

func (appender *recordingAuditAppender) AppendOriginalAccessAudit(
	_ context.Context,
	decision quotaports.AuditDecision,
) (quotaports.AuditRecord, error) {
	appender.decisions = append(appender.decisions, decision)
	expiresAt := decision.GrantExpiresAt
	return quotaports.AuditRecord{
		AuditID:   fmt.Sprintf("audit-%d", len(appender.decisions)),
		Outcome:   decision.Outcome,
		ExpiresAt: expiresAt,
	}, nil
}

func (appender *recordingAuditAppender) lastReason(t *testing.T) string {
	t.Helper()
	if len(appender.decisions) == 0 {
		t.Fatal("expected an audit decision to be appended")
	}
	return appender.decisions[len(appender.decisions)-1].Reason
}

type fakeAssetReader struct {
	asset mediaassetports.OriginalAccessSlice
	found bool
}

func (reader fakeAssetReader) FindOriginalAccessAsset(
	context.Context,
	string,
) (mediaassetports.OriginalAccessSlice, bool, error) {
	return reader.asset, reader.found, nil
}

type fakeVisibilityReader struct {
	visible bool
	calls   int
}

func (reader *fakeVisibilityReader) CanViewerAccessPublishedMedia(
	context.Context,
	string,
	string,
) (bool, error) {
	reader.calls++
	return reader.visible, nil
}

type fakeURLSigner struct{}

func (fakeURLSigner) DeliveryURLUntil(
	_ context.Context,
	objectKey string,
	expiresAt time.Time,
) (string, error) {
	return "https://media.local/" + objectKey +
		"?sign=test&t=" + fmt.Sprint(expiresAt.Unix()), nil
}

type fakeActiveResearchRelease struct {
	releaseID string
	found     bool
}

func (reader fakeActiveResearchRelease) ActiveResearchReleaseID(
	context.Context,
) (string, bool, error) {
	return reader.releaseID, reader.found, nil
}

func releaseAsset(mediaType string, sourceReleaseID string) mediaassetports.OriginalAccessSlice {
	return mediaassetports.OriginalAccessSlice{
		AssetID:          "asset-research-1",
		OwnerID:          "data-release-owner",
		ObjectKey:        "media/objects/sha256/aa/asset-research-1",
		MediaType:        mediaType,
		MimeType:         "image/webp",
		FileSize:         1024,
		ProcessingStatus: "ready",
		AccessPolicy:     "referenced_post",
		SourceReleaseID:  sourceReleaseID,
	}
}

func newResearchQuotaService(
	t *testing.T,
	asset mediaassetports.OriginalAccessSlice,
	visibility *fakeVisibilityReader,
	audits *recordingAuditAppender,
	options ...quotaapp.Option,
) *quotaapp.Service {
	t.Helper()
	return quotaapp.NewService(
		fakeQuotaStore{},
		audits,
		fakeAssetReader{asset: asset, found: true},
		visibility,
		fakeURLSigner{},
		options...,
	)
}

func reserveContext() context.Context {
	return commandmeta.WithIdempotencyKey(
		context.Background(),
		"research-reserve-key",
	)
}

func TestResearchPrincipalReservesActiveReleaseAssetsForView(t *testing.T) {
	for _, mediaType := range []string{"avatar", "image", "video"} {
		t.Run(mediaType, func(t *testing.T) {
			audits := &recordingAuditAppender{}
			visibility := &fakeVisibilityReader{visible: false}
			service := newResearchQuotaService(
				t,
				releaseAsset(mediaType, "release-research-1"),
				visibility,
				audits,
				quotaapp.WithActiveResearchReleaseReader(
					fakeActiveResearchRelease{releaseID: "release-research-1", found: true},
				),
			)

			result, err := service.Reserve(reserveContext(), quotaapp.Command{
				AssetID:           "asset-research-1",
				ViewerID:          "viewer-research",
				Purpose:           "view",
				ResearchPrincipal: true,
			})
			if err != nil {
				t.Fatalf("research view reserve failed: %v", err)
			}
			if result.Status != "granted" || result.OriginalURL == "" {
				t.Fatalf("research reserve result = %+v, want granted with URL", result)
			}
			// research 链不得回退到 Post 可见性判定：头像与主页资产无引用 Post。
			if visibility.calls != 0 {
				t.Fatalf("research reserve consulted post visibility %d times", visibility.calls)
			}
		})
	}
}

func TestResearchPrincipalDenialsFailClosed(t *testing.T) {
	activeRelease := quotaapp.WithActiveResearchReleaseReader(
		fakeActiveResearchRelease{releaseID: "release-research-1", found: true},
	)
	for _, testCase := range []struct {
		name       string
		asset      mediaassetports.OriginalAccessSlice
		purpose    string
		options    []quotaapp.Option
		wantReason string
	}{
		{
			name:       "save purpose is denied",
			asset:      releaseAsset("image", "release-research-1"),
			purpose:    "save",
			options:    []quotaapp.Option{activeRelease},
			wantReason: "research_purpose",
		},
		{
			name:       "unsupported media type is denied",
			asset:      releaseAsset("document", "release-research-1"),
			purpose:    "view",
			options:    []quotaapp.Option{activeRelease},
			wantReason: "unsupported_media_type",
		},
		{
			name:       "foreign release membership is denied",
			asset:      releaseAsset("image", "release-other"),
			purpose:    "view",
			options:    []quotaapp.Option{activeRelease},
			wantReason: "research_release_membership",
		},
		{
			name:    "missing active research release is denied",
			asset:   releaseAsset("image", "release-research-1"),
			purpose: "view",
			options: []quotaapp.Option{
				quotaapp.WithActiveResearchReleaseReader(
					fakeActiveResearchRelease{found: false},
				),
			},
			wantReason: "research_release_membership",
		},
		{
			name:       "missing reader wiring is denied",
			asset:      releaseAsset("image", "release-research-1"),
			purpose:    "view",
			options:    nil,
			wantReason: "research_release_membership",
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			audits := &recordingAuditAppender{}
			service := newResearchQuotaService(
				t,
				testCase.asset,
				&fakeVisibilityReader{visible: true},
				audits,
				testCase.options...,
			)

			_, err := service.Reserve(reserveContext(), quotaapp.Command{
				AssetID:           testCase.asset.AssetID,
				ViewerID:          "viewer-research",
				Purpose:           testCase.purpose,
				ResearchPrincipal: true,
			})
			if err == nil {
				t.Fatal("research reserve must fail closed")
			}
			if reason := audits.lastReason(t); reason != testCase.wantReason {
				t.Fatalf("denial reason = %q, want %q", reason, testCase.wantReason)
			}
		})
	}
}

func TestNormalPrincipalKeepsPostVisibilityChain(t *testing.T) {
	audits := &recordingAuditAppender{}
	visibility := &fakeVisibilityReader{visible: true}
	asset := releaseAsset("image", "")
	service := newResearchQuotaService(t, asset, visibility, audits)

	result, err := service.Reserve(reserveContext(), quotaaapCommandNormal(asset.AssetID))
	if err != nil {
		t.Fatalf("normal reserve failed: %v", err)
	}
	if result.Status != "granted" {
		t.Fatalf("normal reserve result = %+v, want granted", result)
	}
	if visibility.calls != 1 {
		t.Fatalf("normal reserve must consult post visibility once, got %d", visibility.calls)
	}
}

func quotaaapCommandNormal(assetID string) quotaapp.Command {
	return quotaapp.Command{
		AssetID:  assetID,
		ViewerID: "viewer-normal",
		Purpose:  "save",
	}
}

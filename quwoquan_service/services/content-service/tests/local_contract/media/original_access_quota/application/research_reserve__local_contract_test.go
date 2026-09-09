// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
// Data 专属 membership 放行已退役；共享原图签发必须经过普通可见性链。
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

type fakeQuotaStore struct{ calls int }

func (store *fakeQuotaStore) Reserve(_ context.Context, reservation quotamodel.Reservation, _ quotamodel.Policy) (quotaports.ReserveResult, error) {
	store.calls++
	return quotaports.ReserveResult{Reservation: reservation}, nil
}

type recordingAuditAppender struct{ decisions []quotaports.AuditDecision }

func (appender *recordingAuditAppender) AppendOriginalAccessAudit(_ context.Context, decision quotaports.AuditDecision) (quotaports.AuditRecord, error) {
	appender.decisions = append(appender.decisions, decision)
	return quotaports.AuditRecord{AuditID: fmt.Sprintf("audit-%d", len(appender.decisions)), Outcome: decision.Outcome, ExpiresAt: decision.GrantExpiresAt}, nil
}

type fakeAssetReader struct {
	asset mediaassetports.OriginalAccessSlice
	found bool
}

func (reader fakeAssetReader) FindOriginalAccessAsset(context.Context, string) (mediaassetports.OriginalAccessSlice, bool, error) {
	return reader.asset, reader.found, nil
}

type fakeVisibilityReader struct {
	visible bool
	calls   int
}

func (reader *fakeVisibilityReader) CanViewerAccessPublishedMedia(context.Context, string, string) (bool, error) {
	reader.calls++
	return reader.visible, nil
}

type fakeURLSigner struct{ calls int }

func (signer *fakeURLSigner) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	signer.calls++
	return "https://media.example/" + objectKey + "?sign=test&t=" + fmt.Sprint(expiresAt.Unix()), nil
}

func TestSharedOriginalAccessKeepsVisibilityPolicyAndSignedGrant(t *testing.T) {
	for _, test := range []struct {
		name, kind, status, policy, purpose string
		visible, owner                      bool
		wantReason                          string
	}{
		{"view", "image", "ready", "referenced_post", "view", true, false, "authorized"},
		{"save", "image", "ready", "referenced_post", "save", true, false, "authorized"},
		{"owner image", "image", "ready", "owner_only", "save", true, true, "authorized"},
		{"not visible", "image", "ready", "referenced_post", "view", false, false, "post_visibility"},
		{"foreign owner", "image", "ready", "owner_only", "view", true, false, "asset_policy"},
		{"not ready", "image", "pending", "referenced_post", "view", true, false, "asset_not_ready"},
		{"retired avatar bypass", "avatar", "ready", "referenced_post", "view", true, false, "asset_not_ready"},
		{"retired video bypass", "video", "ready", "referenced_post", "view", true, false, "asset_not_ready"},
	} {
		t.Run(test.name, func(t *testing.T) {
			now := time.Date(2026, 9, 9, 0, 0, 0, 0, time.UTC)
			asset := mediaassetports.OriginalAccessSlice{AssetID: "private-image", OwnerID: "owner", ObjectKey: "private/image", MediaType: test.kind, MimeType: "image/webp", FileSize: 1024, ProcessingStatus: test.status, AccessPolicy: test.policy}
			viewer := "viewer"
			if test.owner {
				viewer = "owner"
			}
			quota, audits, visibility, signer := &fakeQuotaStore{}, &recordingAuditAppender{}, &fakeVisibilityReader{visible: test.visible}, &fakeURLSigner{}
			service := quotaapp.NewService(quota, audits, fakeAssetReader{asset, true}, visibility, signer, quotaapp.WithClock(func() time.Time { return now }))
			result, err := service.Reserve(commandmeta.WithIdempotencyKey(context.Background(), "reserve-key"), quotaapp.Command{AssetID: asset.AssetID, ViewerID: viewer, Purpose: test.purpose})
			if len(audits.decisions) != 1 || audits.decisions[0].Reason != test.wantReason {
				t.Fatalf("audit=%+v err=%v", audits.decisions, err)
			}
			if test.wantReason == "authorized" {
				if err != nil || result.Status != "granted" || result.OriginalURL == "" || result.AuditID == "" || !result.ExpiresAt.After(now) || signer.calls != 1 || quota.calls != 1 || visibility.calls != 1 {
					t.Fatalf("shared grant lost policy/quota/audit/TTL: result=%+v err=%v", result, err)
				}
			} else if err == nil || signer.calls != 0 || quota.calls != 0 {
				t.Fatalf("denied asset reached quota/signer: err=%v quota=%d signer=%d", err, quota.calls, signer.calls)
			}
		})
	}
}

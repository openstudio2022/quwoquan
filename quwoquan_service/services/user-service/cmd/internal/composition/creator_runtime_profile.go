package composition

import (
	"context"
	"fmt"
	"strings"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	creatormodel "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

const mediaDeliveryAccessModePublic = "public"

type CreatorRuntimeProfileReader interface {
	FindByExactContentFence(context.Context, creatormodel.ReleaseIdentity, string) (*creatormodel.CreatorRuntimeProfile, bool, error)
}

type CreatorRuntimeProfileAdapter struct{ reader CreatorRuntimeProfileReader }

func NewCreatorRuntimeProfileAdapter(reader CreatorRuntimeProfileReader) *CreatorRuntimeProfileAdapter {
	if reader == nil {
		panic("CreatorRuntimeProfile composition adapter requires reader")
	}
	return &CreatorRuntimeProfileAdapter{reader: reader}
}

func (a *CreatorRuntimeProfileAdapter) FindByExactContentFence(ctx context.Context, fence userports.ContentReleaseFence, identity string) (*userports.CreatorRuntimeProfileView, bool, error) {
	profile, found, err := a.reader.FindByExactContentFence(ctx, creatormodel.ReleaseIdentity{Environment: fence.Environment, SourceOwner: fence.SourceOwner, ReleaseID: fence.ReleaseID, ManifestDigest: fence.ManifestDigest}, identity)
	if err != nil || !found {
		return nil, found, err
	}
	if profile == nil {
		return nil, false, fmt.Errorf("creator release projection is missing")
	}
	if strings.TrimSpace(profile.AvatarAssetID) != "" && strings.TrimSpace(profile.AvatarPublicSliceKey) == "" {
		return nil, false, fmt.Errorf("creator release avatar requires a public slice binding")
	}
	works := make([]userports.CreatorWorkView, 0, len(profile.Works))
	for _, work := range profile.Works {
		works = append(works, mapCreatorWork(work))
	}
	return &userports.CreatorRuntimeProfileView{CreatorID: profile.CreatorID, PersonaID: profile.PersonaID, Handle: profile.Handle, DisplayName: profile.DisplayName, Headline: profile.Headline, Bio: profile.Bio, AvatarURL: profile.AvatarURL, AvatarAssetID: strings.TrimSpace(profile.AvatarAssetID), AvatarAccessMode: creatorAvatarAccessMode(profile), AvatarVersion: profile.AvatarVersion, CoverURL: profile.CoverURL, PublicProfileTagRefs: append([]string(nil), profile.PublicProfileTagRefs...), Roles: append([]string(nil), profile.Roles...), Verticals: append([]string(nil), profile.Verticals...), ExpertiseClaims: append([]string(nil), profile.ExpertiseClaims...), Disclosure: userports.CreatorDisclosureView{Type: profile.Disclosure.Type, DisplayText: profile.Disclosure.DisplayText, Visible: profile.Disclosure.Visible}, Works: works, UpdatedAt: profile.UpdatedAt}, true, nil
}

func (a *CreatorRuntimeProfileAdapter) ListWorksByExactContentFence(ctx context.Context, fence userports.ContentReleaseFence, identity string) ([]userports.CreatorWorkView, bool, error) {
	profile, found, err := a.FindByExactContentFence(ctx, fence, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]userports.CreatorWorkView(nil), profile.Works...), true, nil
}

func creatorAvatarAccessMode(profile *creatormodel.CreatorRuntimeProfile) string {
	if strings.TrimSpace(profile.AvatarAssetID) == "" {
		return ""
	}
	return mediaDeliveryAccessModePublic
}

func mapCreatorWork(work creatormodel.CreatorWorkRef) userports.CreatorWorkView {
	return userports.CreatorWorkView{Ref: work.Ref, Title: work.Title, CoverURL: work.CoverURL, WorkType: work.WorkType, SortOrder: work.SortOrder}
}

var _ userports.CreatorRuntimeProfileReader = (*CreatorRuntimeProfileAdapter)(nil)

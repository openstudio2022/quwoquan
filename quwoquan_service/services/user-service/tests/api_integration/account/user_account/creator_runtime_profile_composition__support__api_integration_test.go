package api_integration

import (
	"context"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	creatormodel "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

type creatorRuntimeProfileTestReader interface {
	FindActiveByPublicIdentity(context.Context, string) (*creatormodel.CreatorRuntimeProfile, bool, error)
	ListActiveWorks(context.Context, string) ([]creatormodel.CreatorWorkRef, bool, error)
}

type creatorRuntimeProfileTestAdapter struct {
	reader creatorRuntimeProfileTestReader
}

func newCreatorRuntimeProfileTestAdapter(reader creatorRuntimeProfileTestReader) *creatorRuntimeProfileTestAdapter {
	return &creatorRuntimeProfileTestAdapter{reader: reader}
}

func (a *creatorRuntimeProfileTestAdapter) FindActiveByPublicIdentity(
	ctx context.Context,
	identity string,
) (*userports.CreatorRuntimeProfileView, bool, error) {
	profile, found, err := a.reader.FindActiveByPublicIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return &userports.CreatorRuntimeProfileView{
		CreatorID:            profile.CreatorID,
		PersonaID:            profile.PersonaID,
		Handle:               profile.Handle,
		DisplayName:          profile.DisplayName,
		Headline:             profile.Headline,
		Bio:                  profile.Bio,
		AvatarURL:            profile.AvatarURL,
		AvatarVersion:        profile.AvatarVersion,
		CoverURL:             profile.CoverURL,
		PublicProfileTagRefs: append([]string(nil), profile.PublicProfileTagRefs...),
		Roles:                append([]string(nil), profile.Roles...),
		Verticals:            append([]string(nil), profile.Verticals...),
		ExpertiseClaims:      append([]string(nil), profile.ExpertiseClaims...),
		Disclosure: userports.CreatorDisclosureView{
			Type:        profile.Disclosure.Type,
			DisplayText: profile.Disclosure.DisplayText,
			Visible:     profile.Disclosure.Visible,
		},
		Works:     mapCreatorRuntimeProfileTestWorks(profile.Works),
		UpdatedAt: profile.UpdatedAt,
	}, true, nil
}

func (a *creatorRuntimeProfileTestAdapter) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]userports.CreatorWorkView, bool, error) {
	works, found, err := a.reader.ListActiveWorks(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return mapCreatorRuntimeProfileTestWorks(works), true, nil
}

func mapCreatorRuntimeProfileTestWorks(works []creatormodel.CreatorWorkRef) []userports.CreatorWorkView {
	result := make([]userports.CreatorWorkView, 0, len(works))
	for _, work := range works {
		result = append(result, userports.CreatorWorkView{
			Ref:       work.Ref,
			Title:     work.Title,
			CoverURL:  work.CoverURL,
			WorkType:  work.WorkType,
			SortOrder: work.SortOrder,
		})
	}
	return result
}

var _ userports.CreatorRuntimeProfileReader = (*creatorRuntimeProfileTestAdapter)(nil)

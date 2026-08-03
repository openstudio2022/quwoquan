package composition

import (
	"context"

	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
	creatormodel "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

type CreatorRuntimeProfileReader interface {
	FindActiveByPublicIdentity(context.Context, string) (*creatormodel.CreatorRuntimeProfile, bool, error)
	ListActiveWorks(context.Context, string) ([]creatormodel.CreatorWorkRef, bool, error)
}

type CreatorRuntimeProfileAdapter struct{ reader CreatorRuntimeProfileReader }

func NewCreatorRuntimeProfileAdapter(reader CreatorRuntimeProfileReader) *CreatorRuntimeProfileAdapter {
	if reader == nil {
		panic("CreatorRuntimeProfile composition adapter requires reader")
	}
	return &CreatorRuntimeProfileAdapter{reader: reader}
}

func (a *CreatorRuntimeProfileAdapter) FindActiveByPublicIdentity(
	ctx context.Context,
	identity string,
) (*userports.CreatorRuntimeProfileView, bool, error) {
	profile, found, err := a.reader.FindActiveByPublicIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	works := make([]userports.CreatorWorkView, 0, len(profile.Works))
	for _, work := range profile.Works {
		works = append(works, mapCreatorWork(work))
	}
	return &userports.CreatorRuntimeProfileView{
		CreatorID: profile.CreatorID, PersonaID: profile.PersonaID,
		Handle: profile.Handle, DisplayName: profile.DisplayName,
		Headline: profile.Headline, Bio: profile.Bio, AvatarURL: profile.AvatarURL,
		AvatarVersion: profile.AvatarVersion, CoverURL: profile.CoverURL,
		PublicProfileTagRefs: append([]string(nil), profile.PublicProfileTagRefs...),
		Roles:                append([]string(nil), profile.Roles...),
		Verticals:            append([]string(nil), profile.Verticals...),
		ExpertiseClaims:      append([]string(nil), profile.ExpertiseClaims...),
		Disclosure: userports.CreatorDisclosureView{
			Type: profile.Disclosure.Type, DisplayText: profile.Disclosure.DisplayText,
			Visible: profile.Disclosure.Visible,
		},
		Works: works, UpdatedAt: profile.UpdatedAt,
	}, true, nil
}

func (a *CreatorRuntimeProfileAdapter) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]userports.CreatorWorkView, bool, error) {
	works, found, err := a.reader.ListActiveWorks(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	result := make([]userports.CreatorWorkView, 0, len(works))
	for _, work := range works {
		result = append(result, mapCreatorWork(work))
	}
	return result, true, nil
}

func mapCreatorWork(work creatormodel.CreatorWorkRef) userports.CreatorWorkView {
	return userports.CreatorWorkView{
		Ref: work.Ref, Title: work.Title, CoverURL: work.CoverURL,
		WorkType: work.WorkType, SortOrder: work.SortOrder,
	}
}

var _ userports.CreatorRuntimeProfileReader = (*CreatorRuntimeProfileAdapter)(nil)

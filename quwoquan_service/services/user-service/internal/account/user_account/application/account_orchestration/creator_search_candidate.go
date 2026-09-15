package application

import (
	"context"
	"errors"
	"fmt"
	rt "quwoquan_service/runtime/search"
	model "quwoquan_service/services/user-service/internal/account/user_account/domain/user/model"
)

var ErrCreatorCandidateInvalid = errors.New("invalid Creator search candidate")

type CreatorSearchCandidateReader interface {
	Read(context.Context, rt.ReleaseCandidateBinding) (*rt.CreatorSearchCandidateSnapshot, error)
}
type CreatorSearchPersonaReader interface {
	FindByPersonaID(context.Context, string) (*model.Persona, error)
	FindByUserHandle(context.Context, string) (*model.Persona, error)
}
type CreatorSearchAccountReader interface {
	FindByID(context.Context, string) (*model.UserProfile, error)
}
type CreatorSearchCandidateQueryFacade struct {
	reader      CreatorSearchCandidateReader
	personas    CreatorSearchPersonaReader
	accounts    CreatorSearchAccountReader
	environment string
}
type CreatorSearchCandidateResult struct {
	Found    bool                               `json:"found"`
	Snapshot *rt.CreatorSearchCandidateSnapshot `json:"snapshot"`
}

func NewCreatorSearchCandidateQueryFacade(reader CreatorSearchCandidateReader, personas CreatorSearchPersonaReader, accounts CreatorSearchAccountReader, environment string) *CreatorSearchCandidateQueryFacade {
	return &CreatorSearchCandidateQueryFacade{reader, personas, accounts, environment}
}
func (f *CreatorSearchCandidateQueryFacade) Read(ctx context.Context, b rt.ReleaseCandidateBinding) (CreatorSearchCandidateResult, error) {
	if b.Validate() != nil || b.Environment != f.environment {
		return CreatorSearchCandidateResult{}, fmt.Errorf("%w: deployment", ErrCreatorCandidateInvalid)
	}
	if f.reader == nil || f.personas == nil || f.accounts == nil {
		return CreatorSearchCandidateResult{}, fmt.Errorf("candidate dependency unavailable")
	}
	snapshot, err := f.reader.Read(ctx, b)
	if err != nil || snapshot == nil {
		return CreatorSearchCandidateResult{}, err
	}
	for _, p := range snapshot.Profiles {
		persona, err := f.personas.FindByPersonaID(ctx, p.PersonaID)
		if err != nil {
			return CreatorSearchCandidateResult{}, err
		}
		if persona != nil {
			return CreatorSearchCandidateResult{}, fmt.Errorf("%w: persona collision", ErrCreatorCandidateInvalid)
		}
		persona, err = f.personas.FindByUserHandle(ctx, p.UserHandle)
		if err != nil {
			return CreatorSearchCandidateResult{}, err
		}
		if persona != nil {
			return CreatorSearchCandidateResult{}, fmt.Errorf("%w: handle collision", ErrCreatorCandidateInvalid)
		}
		account, err := f.accounts.FindByID(ctx, p.ObjectID)
		if err != nil {
			return CreatorSearchCandidateResult{}, err
		}
		if account != nil {
			return CreatorSearchCandidateResult{}, fmt.Errorf("%w: account collision", ErrCreatorCandidateInvalid)
		}
	}
	return CreatorSearchCandidateResult{Found: true, Snapshot: snapshot}, nil
}

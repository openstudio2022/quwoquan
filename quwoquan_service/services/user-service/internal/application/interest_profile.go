package application

import (
	"context"
	"time"
)

// InterestTopInterest is one ranked interest entry within a user profile.
type InterestTopInterest struct {
	TagRef    string  `json:"tagRef" bson:"tagRef"`
	Dimension string  `json:"dimension" bson:"dimension"`
	Score     float64 `json:"score" bson:"score"`
	Level     int     `json:"level" bson:"level"`
}

// InterestProfileView is the user-domain derived interest read model
// (rm_user_profile_view.interestProfile). It is intentionally both the
// projection storage shape and the read DTO: a CQRS read model whose storage
// is shaped for reads, so there is a single type and zero mapping drift.
type InterestProfileView struct {
	UserID            string                `json:"userId" bson:"-"`
	TopInterests      []InterestTopInterest `json:"topInterests" bson:"topInterests"`
	DimensionTops     map[string][]string   `json:"dimensionTops" bson:"dimensionTops"`
	LifecycleStage    string                `json:"lifecycleStage" bson:"lifecycleStage"`
	FreshnessDays     int                   `json:"freshnessDays" bson:"freshnessDays"`
	DecayHalfLifeDays int                   `json:"decayHalfLifeDays" bson:"decayHalfLifeDays"`
	RecomputedAt      time.Time             `json:"recomputedAt" bson:"recomputedAt"`
	// Segments are rule-based population memberships, stored at the
	// rm_user_profile_view top level (not inside the interestProfile
	// sub-document), so bson:"-" here; the reader fills it separately.
	Segments []string `json:"segments" bson:"-"`
}

// InterestProfileReader reads the derived interest profile read model.
// Implemented by infrastructure (MongoDB rm_user_profile_view).
type InterestProfileReader interface {
	GetInterestProfile(ctx context.Context, userID string) (*InterestProfileView, error)
}

// InterestProfileService exposes interest-profile reads to adapters.
type InterestProfileService struct {
	reader InterestProfileReader
}

func NewInterestProfileService(reader InterestProfileReader) *InterestProfileService {
	return &InterestProfileService{reader: reader}
}

// Get returns the user's interest profile. When the profile has not been
// derived yet it returns an empty profile (lifecycleStage="new") instead of an
// error so consumers (assistant / recommendation) never special-case 404.
func (s *InterestProfileService) Get(ctx context.Context, userID string) (*InterestProfileView, error) {
	empty := &InterestProfileView{
		UserID:         userID,
		TopInterests:   []InterestTopInterest{},
		DimensionTops:  map[string][]string{},
		LifecycleStage: "new",
		Segments:       []string{},
	}
	if s == nil || s.reader == nil {
		return empty, nil
	}
	view, err := s.reader.GetInterestProfile(ctx, userID)
	if err != nil {
		return nil, err
	}
	if view == nil {
		return empty, nil
	}
	view.UserID = userID
	if view.TopInterests == nil {
		view.TopInterests = []InterestTopInterest{}
	}
	if view.DimensionTops == nil {
		view.DimensionTops = map[string][]string{}
	}
	if view.LifecycleStage == "" {
		view.LifecycleStage = "new"
	}
	if view.Segments == nil {
		view.Segments = []string{}
	}
	return view, nil
}

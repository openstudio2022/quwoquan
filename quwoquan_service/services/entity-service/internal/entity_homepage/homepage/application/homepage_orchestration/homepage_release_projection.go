package application

import (
	"context"
	"time"

	homepageapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

type HomepageReleaseIdentity = homepageports.ReleaseIdentity
type HomepageReleaseStageRequest = homepageapp.ReleaseStageRequest
type HomepageReleaseStageReport = homepageapp.ReleaseStageReport
type HomepageReleaseCandidateReceipt = homepageapp.HomepageReleaseCandidateReceipt

var NormalizeHomepageReleaseIdentity = homepageapp.NormalizeReleaseIdentity

func (s *HomepageService) StageHomepageReleaseCandidate(
	ctx context.Context,
	request HomepageReleaseStageRequest,
	now time.Time,
) (HomepageReleaseStageReport, error) {
	return homepageapp.StageReleaseCandidate(ctx, s.store, request, now)
}

func (s *HomepageService) QueryHomepageReleaseCandidate(
	ctx context.Context,
	identity HomepageReleaseIdentity,
) (HomepageReleaseCandidateReceipt, error) {
	return homepageapp.QueryReleaseCandidate(ctx, s.store, identity)
}

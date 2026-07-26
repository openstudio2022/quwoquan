package application

import (
	"context"
	"strings"
	"time"

	"quwoquan_service/runtime/operation"
	entitygenerated "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	claimapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/application"
	claimmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_claim_request/domain/model"
	statusapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/application"
	statusmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_status_report/domain/model"
)

// 以下 DTO 仅维持既有 HTTP wire；状态与持久化全部委托独立对象 packet。
type HomepageClaimRequest struct {
	ClaimRequestID       string     `json:"claimRequestId"`
	Version              int64      `json:"version"`
	HomepageID           string     `json:"homepageId"`
	RequesterPersonaID   string     `json:"requesterPersonaId"`
	ClaimTier            string     `json:"claimTier"`
	BusinessLicenseURL   string     `json:"businessLicenseUrl,omitempty"`
	ContactPhone         string     `json:"contactPhone,omitempty"`
	IdentityCardFrontURL string     `json:"identityCardFrontUrl,omitempty"`
	IdentityCardBackURL  string     `json:"identityCardBackUrl,omitempty"`
	Note                 string     `json:"note,omitempty"`
	Status               string     `json:"status"`
	ReviewerAccountID    string     `json:"reviewerAccountId,omitempty"`
	ReviewNote           string     `json:"reviewNote,omitempty"`
	CreatedAt            time.Time  `json:"createdAt"`
	UpdatedAt            time.Time  `json:"updatedAt"`
	ReviewedAt           *time.Time `json:"reviewedAt,omitempty"`
}

type HomepageStatusReport struct {
	ReportID          string     `json:"reportId"`
	Version           int64      `json:"version"`
	HomepageID        string     `json:"homepageId"`
	ReporterPersonaID string     `json:"reporterPersonaId"`
	Reason            string     `json:"reason"`
	Description       string     `json:"description,omitempty"`
	EvidenceURLs      []string   `json:"evidenceUrls,omitempty"`
	Status            string     `json:"status"`
	ReviewerAccountID string     `json:"reviewerAccountId,omitempty"`
	ReviewNote        string     `json:"reviewNote,omitempty"`
	CreatedAt         time.Time  `json:"createdAt"`
	UpdatedAt         time.Time  `json:"updatedAt"`
	ReviewedAt        *time.Time `json:"reviewedAt,omitempty"`
}

type ClaimRequestInput struct {
	RequesterPersonaID   string `json:"requesterPersonaId"`
	ClaimTier            string `json:"claimTier"`
	BusinessLicenseURL   string `json:"businessLicenseUrl"`
	ContactPhone         string `json:"contactPhone"`
	IdentityCardFrontURL string `json:"identityCardFrontUrl"`
	IdentityCardBackURL  string `json:"identityCardBackUrl"`
	Note                 string `json:"note"`
}

type ClaimReviewInput struct {
	Status     string `json:"status"`
	ReviewNote string `json:"reviewNote"`
}

type StatusReportInput struct {
	ReporterPersonaID string   `json:"reporterPersonaId"`
	Reason            string   `json:"reason"`
	Description       string   `json:"description"`
	EvidenceURLs      []string `json:"evidenceUrls"`
}

type StatusReportReviewInput struct {
	Status     string `json:"status"`
	ReviewNote string `json:"reviewNote"`
}

func (s *HomepageService) ListHomepageClaimRequests(
	ctx context.Context,
	homepageID string,
	status string,
	cursor string,
	limit int,
) (claimapp.ClaimRequestSlice, error) {
	if s.claims == nil {
		return claimapp.ClaimRequestSlice{},
			entitygenerated.AppErrorFromInternalError("homepage claim facade is not configured")
	}
	targetStatus := claimmodel.Status(strings.TrimSpace(status))
	switch targetStatus {
	case "", claimmodel.StatusPendingReview, claimmodel.StatusApproved, claimmodel.StatusRejected:
	default:
		return claimapp.ClaimRequestSlice{},
			entitygenerated.AppErrorFromInvalidArgument("unsupported homepage claim queue status")
	}
	return s.claims.ListQueue(ctx, claimapp.QueueQuery{
		HomepageID: strings.TrimSpace(homepageID),
		Status:     targetStatus,
		Cursor:     strings.TrimSpace(cursor),
		Limit:      limit,
	})
}

func (s *HomepageService) ListHomepageStatusReports(
	ctx context.Context,
	homepageID string,
	status string,
	cursor string,
	limit int,
) (statusapp.StatusReportSlice, error) {
	if s.statusReports == nil {
		return statusapp.StatusReportSlice{},
			entitygenerated.AppErrorFromInternalError("homepage status report facade is not configured")
	}
	targetStatus := statusmodel.Status(strings.TrimSpace(status))
	switch targetStatus {
	case "", statusmodel.StatusPendingReview, statusmodel.StatusConfirmedOffline, statusmodel.StatusDismissed:
	default:
		return statusapp.StatusReportSlice{},
			entitygenerated.AppErrorFromInvalidArgument("unsupported homepage status report queue status")
	}
	return s.statusReports.ListQueue(ctx, statusapp.QueueQuery{
		HomepageID: strings.TrimSpace(homepageID),
		Status:     targetStatus,
		Cursor:     strings.TrimSpace(cursor),
		Limit:      limit,
	})
}

func (s *HomepageService) CreateHomepageClaimRequest(
	ctx context.Context,
	homepageID string,
	input ClaimRequestInput,
) (*HomepageClaimRequest, error) {
	if s.claims == nil {
		return nil, entitygenerated.AppErrorFromInternalError("homepage claim facade is not configured")
	}
	view, err := s.claims.Create(ctx, claimapp.CreateCommand{
		HomepageID:           strings.TrimSpace(homepageID),
		ActorPersonaID:       strings.TrimSpace(input.RequesterPersonaID),
		ClaimTier:            claimmodel.ClaimTier(strings.TrimSpace(input.ClaimTier)),
		BusinessLicenseURL:   strings.TrimSpace(input.BusinessLicenseURL),
		ContactPhone:         strings.TrimSpace(input.ContactPhone),
		IdentityCardFrontURL: strings.TrimSpace(input.IdentityCardFrontURL),
		IdentityCardBackURL:  strings.TrimSpace(input.IdentityCardBackURL),
		Note:                 strings.TrimSpace(input.Note),
	})
	if err != nil {
		return nil, err
	}
	result := claimViewToHTTP(view)
	return &result, nil
}

func (s *HomepageService) ReviewHomepageClaimRequest(
	ctx context.Context,
	homepageID string,
	claimRequestID string,
	input ClaimReviewInput,
) (*HomepageClaimRequest, error) {
	if s.claims == nil {
		return nil, entitygenerated.AppErrorFromInternalError("homepage claim facade is not configured")
	}
	view, err := s.claims.Review(ctx, claimapp.ReviewCommand{
		HomepageID:     strings.TrimSpace(homepageID),
		ClaimRequestID: strings.TrimSpace(claimRequestID),
		ActorAccountID: accountActor(ctx),
		TargetStatus:   claimmodel.Status(strings.TrimSpace(input.Status)),
		ReviewNote:     strings.TrimSpace(input.ReviewNote),
	})
	if err != nil {
		return nil, err
	}
	result := claimViewToHTTP(view)
	return &result, nil
}

func (s *HomepageService) CreateHomepageStatusReport(
	ctx context.Context,
	homepageID string,
	input StatusReportInput,
) (*HomepageStatusReport, error) {
	if s.statusReports == nil {
		return nil, entitygenerated.AppErrorFromInternalError("homepage status report facade is not configured")
	}
	view, err := s.statusReports.Create(ctx, statusapp.CreateCommand{
		HomepageID:     strings.TrimSpace(homepageID),
		ActorPersonaID: strings.TrimSpace(input.ReporterPersonaID),
		Reason:         statusmodel.Reason(strings.TrimSpace(input.Reason)),
		Description:    strings.TrimSpace(input.Description),
		EvidenceURLs:   append([]string(nil), input.EvidenceURLs...),
	})
	if err != nil {
		return nil, err
	}
	result := statusViewToHTTP(view)
	return &result, nil
}

func (s *HomepageService) ReviewHomepageStatusReport(
	ctx context.Context,
	homepageID string,
	reportID string,
	input StatusReportReviewInput,
) (*HomepageStatusReport, error) {
	if s.statusReports == nil {
		return nil, entitygenerated.AppErrorFromInternalError("homepage status report facade is not configured")
	}
	view, err := s.statusReports.Review(ctx, statusapp.ReviewCommand{
		HomepageID:     strings.TrimSpace(homepageID),
		ReportID:       strings.TrimSpace(reportID),
		ActorAccountID: accountActor(ctx),
		TargetStatus:   statusmodel.Status(strings.TrimSpace(input.Status)),
		ReviewNote:     strings.TrimSpace(input.ReviewNote),
	})
	if err != nil {
		return nil, err
	}
	result := statusViewToHTTP(view)
	return &result, nil
}

func claimViewToHTTP(view claimapp.ClaimRequestView) HomepageClaimRequest {
	return HomepageClaimRequest{
		ClaimRequestID:       view.ClaimRequestID,
		Version:              view.Version,
		HomepageID:           view.HomepageID,
		RequesterPersonaID:   view.RequesterPersonaID,
		ClaimTier:            string(view.ClaimTier),
		BusinessLicenseURL:   view.BusinessLicenseURL,
		ContactPhone:         view.ContactPhone,
		IdentityCardFrontURL: view.IdentityCardFrontURL,
		IdentityCardBackURL:  view.IdentityCardBackURL,
		Note:                 view.Note,
		Status:               string(view.Status),
		ReviewerAccountID:    view.ReviewerAccountID,
		ReviewNote:           view.ReviewNote,
		CreatedAt:            view.CreatedAt,
		UpdatedAt:            view.UpdatedAt,
		ReviewedAt:           view.ReviewedAt,
	}
}

func statusViewToHTTP(view statusapp.StatusReportView) HomepageStatusReport {
	return HomepageStatusReport{
		ReportID:          view.ReportID,
		Version:           view.Version,
		HomepageID:        view.HomepageID,
		ReporterPersonaID: view.ReporterPersonaID,
		Reason:            string(view.Reason),
		Description:       view.Description,
		EvidenceURLs:      append([]string(nil), view.EvidenceURLs...),
		Status:            string(view.Status),
		ReviewerAccountID: view.ReviewerAccountID,
		ReviewNote:        view.ReviewNote,
		CreatedAt:         view.CreatedAt,
		UpdatedAt:         view.UpdatedAt,
		ReviewedAt:        view.ReviewedAt,
	}
}

func accountActor(ctx context.Context) string {
	if invocation, ok := operation.FromContext(ctx); ok {
		return strings.TrimSpace(invocation.Actor.AccountID)
	}
	return ""
}

package governance

import (
	"context"
	"strings"

	postports "quwoquan_service/services/content-service/internal/domain/post/ports"
)

// ManualReviewPublicationSafetyGate 是安全的人工审核模式，不是 allow fallback。
// 在未装配可信机器审核 provider 的环境中，所有有效提交均进入不可公开 pending_review。
type ManualReviewPublicationSafetyGate struct{}

func NewManualReviewPublicationSafetyGate() *ManualReviewPublicationSafetyGate {
	return &ManualReviewPublicationSafetyGate{}
}

func (*ManualReviewPublicationSafetyGate) EvaluatePublication(
	_ context.Context,
	request postports.PublicationSafetyRequest,
) (postports.PublicationSafetyResult, error) {
	if strings.TrimSpace(request.PostID) == "" ||
		strings.TrimSpace(request.PersonaID) == "" ||
		strings.TrimSpace(request.ContentDigest) == "" {
		return postports.PublicationSafetyResult{
			Decision:   postports.PublicationSafetyReject,
			ReasonCode: "publication_safety_identity_incomplete",
		}, nil
	}
	return postports.PublicationSafetyResult{
		Decision:   postports.PublicationSafetyReview,
		ReasonCode: "manual_review_required",
	}, nil
}

var _ postports.PublicationSafetyGate = (*ManualReviewPublicationSafetyGate)(nil)

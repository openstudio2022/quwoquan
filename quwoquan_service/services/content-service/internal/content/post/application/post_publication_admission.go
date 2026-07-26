package post

import (
	"context"
	"fmt"
	"strings"
	"time"
	"unicode/utf8"

	rterr "quwoquan_service/runtime/errors"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postmodel "quwoquan_service/services/content-service/internal/content/post/domain/model"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postsemantic "quwoquan_service/services/content-service/internal/content/post/domain/semantic"
)

func validatePostPublicationLimits(post *postmodel.Post) error {
	if post == nil {
		return contentgenerated.AppErrorFromInvalidArgument(
			"publication payload is required",
		)
	}
	checks := []struct {
		field string
		value string
		limit int
	}{
		{"title", post.Title, contentgenerated.PostPublicationTitleMaxRunes},
		{"body", post.Body, contentgenerated.PostPublicationMicroBodyMaxRunes},
		{
			"articleMarkdown",
			post.ArticleMarkdown,
			contentgenerated.PostPublicationArticleMarkdownMaxRunes,
		},
		{"summary", post.Summary, contentgenerated.PostPublicationSummaryMaxRunes},
	}
	for _, check := range checks {
		actual := utf8.RuneCountInString(check.value)
		if actual <= check.limit {
			continue
		}
		return contentgenerated.AppErrorFromContentTooLong(
			fmt.Sprintf(
				"%s contains %d runes; maximum is %d",
				check.field,
				actual,
				check.limit,
			),
		).WithContextAttributes(
			rterr.RuntimeErrorContextAttribute{Key: "field", Value: check.field},
			rterr.RuntimeErrorContextAttribute{
				Key: "limit", Value: fmt.Sprintf("%d", check.limit),
			},
			rterr.RuntimeErrorContextAttribute{
				Key: "actual", Value: fmt.Sprintf("%d", actual),
			},
		)
	}
	mentionCount := len(postsemantic.Rows(post.SemanticMentions))
	if mentionCount > contentgenerated.PostPublicationSemanticMentionsMaxItems {
		return contentgenerated.AppErrorFromContentTooLong(
			fmt.Sprintf(
				"semanticMentions contains %d items; maximum is %d",
				mentionCount,
				contentgenerated.PostPublicationSemanticMentionsMaxItems,
			),
		).WithContextAttributes(
			rterr.RuntimeErrorContextAttribute{
				Key: "field", Value: "semanticMentions",
			},
			rterr.RuntimeErrorContextAttribute{
				Key: "limit",
				Value: fmt.Sprintf(
					"%d",
					contentgenerated.PostPublicationSemanticMentionsMaxItems,
				),
			},
			rterr.RuntimeErrorContextAttribute{
				Key: "actual", Value: fmt.Sprintf("%d", mentionCount),
			},
		)
	}
	return nil
}

func (s *PostService) admitPostPublication(
	ctx context.Context,
	command SubmitPostPublicationCommand,
	post *postmodel.Post,
	now time.Time,
) (postports.PublicationSafetyDecision, error) {
	if s == nil || s.publicationRateGate == nil || s.publicationSafetyGate == nil {
		return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"Post publication admission ports are not configured",
		)
	}
	rateDecision, err := s.publicationRateGate.AdmitPublication(
		ctx,
		postports.PublicationRateRequest{
			PersonaID:       command.AuthorID,
			PublishIntentID: command.PublishIntentID,
			OccurredAt:      now,
		},
	)
	if err != nil {
		return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"Post publication rate gate unavailable: " + err.Error(),
		)
	}
	if !rateDecision.Allowed {
		retryAfter := rateDecision.RetryAfter
		if retryAfter <= 0 {
			retryAfter = time.Duration(
				contentgenerated.PostPublicationPersonaRateWindowSeconds,
			) * time.Second
		}
		return "", contentgenerated.AppErrorFromRateLimited(
			"Post publication rate limit exceeded",
		).WithContextAttributes(
			rterr.RuntimeErrorContextAttribute{
				Key: "retryAfterSeconds",
				Value: fmt.Sprintf(
					"%d",
					max(int64(1), int64(retryAfter/time.Second)),
				),
			},
		)
	}
	result, safetyErr := s.publicationSafetyGate.EvaluatePublication(
		ctx,
		postports.PublicationSafetyRequest{
			PostID:               post.ID,
			PublishIntentID:      command.PublishIntentID,
			PersonaID:            command.AuthorID,
			ContentType:          post.ContentType,
			Title:                post.Title,
			Body:                 post.Body,
			ArticleMarkdown:      post.ArticleMarkdown,
			SemanticMentionCount: len(postsemantic.Rows(post.SemanticMentions)),
			ContentDigest:        post.ContentDigest,
		},
	)
	if safetyErr != nil {
		s.logger.Warn(
			"publication safety gate unavailable; routing to manual review",
			"error",
			safetyErr,
			"contentType",
			post.ContentType,
		)
		return postports.PublicationSafetyReview, nil
	}
	switch result.Decision {
	case postports.PublicationSafetyAllow:
		return result.Decision, nil
	case postports.PublicationSafetyReview,
		postports.PublicationSafetyUnavailable:
		return postports.PublicationSafetyReview, nil
	case postports.PublicationSafetyReject:
		return "", contentgenerated.AppErrorFromPublicationRejected(
			defaultString(
				strings.TrimSpace(result.ReasonCode),
				"publication safety gate rejected content",
			),
		)
	default:
		return "", contentgenerated.AppErrorFromRequiredDependencyUnavailable(
			"Post publication safety gate returned an unsupported decision",
		)
	}
}

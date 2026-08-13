// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t4
// spec_ref: specs/feature-tree/discovery-content/publish-comment-reaction/text-post-commercial-publication/spec.md#gwt-003.t5
package post_test

import (
	"context"
	"errors"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

type fixedRateGate struct {
	decision postports.PublicationRateDecision
	err      error
}

func (g fixedRateGate) AdmitPublication(
	context.Context,
	postports.PublicationRateRequest,
) (postports.PublicationRateDecision, error) {
	return g.decision, g.err
}

func TestPostPublicationAdmissionEnforcesTextLimitsBeforeWriting(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(
		BindDataPorts(store),
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	)
	command := testPublicationCommand("intent-too-long", "draft-too-long")
	command.Content.Title = strings.Repeat(
		"文",
		contentgenerated.PostPublicationTitleMaxRunes+1,
	)

	_, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			command.PublishIntentID,
		),
		command,
	)
	requirePublicationErrorCode(t, err, contentgenerated.ErrContentTooLong.Error())
	if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
		t.Fatalf("over-limit publication wrote Post: %+v", posts)
	}
	if len(store.OutboxEvents()) != 0 {
		t.Fatalf("over-limit publication wrote outbox")
	}
}

func TestPostPublicationAdmissionRoutesReviewAndUnavailableToPending(t *testing.T) {
	for _, testCase := range []struct {
		name string
		gate postports.PublicationSafetyGate
	}{
		{
			name: "explicit review",
			gate: testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyReview,
			},
		},
		{
			name: "provider unavailable",
			gate: testsupport.FixedPublicationSafetyGate{
				Err: errors.New("provider timeout"),
			},
		},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(nil)
			service := NewPostService(
				BindDataPorts(store),
				WithPublicationAdmission(
					testsupport.AllowPublicationRateGate{},
					testCase.gate,
				),
			)
			command := testPublicationCommand(
				"intent-"+strings.ReplaceAll(testCase.name, " ", "-"),
				"draft-"+strings.ReplaceAll(testCase.name, " ", "-"),
			)
			receipt, err := service.SubmitPostPublication(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					command.PublishIntentID,
				),
				command,
			)
			if err != nil {
				t.Fatal(err)
			}
			if receipt.State != "pending_review" {
				t.Fatalf("receipt must be pending_review: %+v", receipt)
			}
			stored, found := store.FindByID(context.Background(), receipt.PostID)
			if !found ||
				stored.Status != "pending_review" ||
				stored.ModerationStatus != "pending" ||
				stored.PublishedAt != (time.Time{}) {
				t.Fatalf("pending Post state mismatch: %+v", stored)
			}
			events := store.OutboxEvents()
			if len(events) != 1 ||
				events[0].EventType != "PostSubmittedForReview" {
				t.Fatalf("pending publication event mismatch: %+v", events)
			}
			if public := store.ListPublished(
				context.Background(),
				10,
				"",
			); len(public) != 0 {
				t.Fatalf("pending Post leaked into public collection: %+v", public)
			}
		})
	}
}

func TestPostPublicationAdmissionRejectAndRateFailureWriteNothing(t *testing.T) {
	tests := []struct {
		name      string
		rate      postports.PublicationRateGate
		safety    postports.PublicationSafetyGate
		errorCode string
	}{
		{
			name: "safety reject",
			rate: testsupport.AllowPublicationRateGate{},
			safety: testsupport.FixedPublicationSafetyGate{
				Decision: postports.PublicationSafetyReject,
			},
			errorCode: contentgenerated.ErrPublicationRejected.Error(),
		},
		{
			name: "rate limited",
			rate: fixedRateGate{decision: postports.PublicationRateDecision{
				RetryAfter: time.Minute,
			}},
			safety:    testsupport.FixedPublicationSafetyGate{},
			errorCode: contentgenerated.ErrRateLimited.Error(),
		},
		{
			name:      "rate dependency unavailable",
			rate:      fixedRateGate{err: errors.New("redis unavailable")},
			safety:    testsupport.FixedPublicationSafetyGate{},
			errorCode: contentgenerated.ErrRequiredDependencyUnavailable.Error(),
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(nil)
			service := NewPostService(
				BindDataPorts(store),
				WithPublicationAdmission(testCase.rate, testCase.safety),
			)
			command := testPublicationCommand(
				"intent-"+strings.ReplaceAll(testCase.name, " ", "-"),
				"draft-"+strings.ReplaceAll(testCase.name, " ", "-"),
			)
			_, err := service.SubmitPostPublication(
				commandmeta.WithIdempotencyKey(
					context.Background(),
					command.PublishIntentID,
				),
				command,
			)
			requirePublicationErrorCode(t, err, testCase.errorCode)
			if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
				t.Fatalf("rejected admission wrote Post: %+v", posts)
			}
			if len(store.OutboxEvents()) != 0 {
				t.Fatalf("rejected admission wrote outbox")
			}
		})
	}
}

func TestPostPublicationAdmissionMissingPortsFailsClosed(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := NewPostService(BindDataPorts(store))
	command := testPublicationCommand("intent-no-ports", "draft-no-ports")
	_, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(
			context.Background(),
			command.PublishIntentID,
		),
		command,
	)
	requirePublicationErrorCode(
		t,
		err,
		contentgenerated.ErrRequiredDependencyUnavailable.Error(),
	)
}

func requirePublicationErrorCode(t *testing.T, err error, expected string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected error code %s", expected)
	}
	if !strings.Contains(err.Error(), expected) {
		t.Fatalf("expected error code %s, got %v", expected, err)
	}
}

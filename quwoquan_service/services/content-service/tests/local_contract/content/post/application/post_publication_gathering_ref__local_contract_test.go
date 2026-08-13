package post_test

import (
	"context"
	"encoding/json"
	"fmt"
	"testing"

	"quwoquan_service/runtime/commandmeta"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	"quwoquan_service/services/content-service/internal/content/post/infrastructure/testsupport"
)

// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#open-005
//
// 共同经历回流引用（post.gatheringRef）的诚实红线：只有 Circle owner 证明作者
// 当前持有 active Participation 时才允许落库；端口未装配、Circle 不可用或
// 参与状态不成立一律 fail-closed，不得半持久化，也不得静默剥离字段冒充成功。

type gatheringParticipationReaderDouble struct {
	status postports.GatheringParticipationStatus
	err    error
	calls  int
}

func (double *gatheringParticipationReaderDouble) GetParticipationStatus(
	_ context.Context,
	gatheringID string,
	personaID string,
) (postports.GatheringParticipationStatus, error) {
	double.calls++
	if double.err != nil {
		return postports.GatheringParticipationStatus{}, double.err
	}
	status := double.status
	if status.GatheringID == "" {
		status.GatheringID = gatheringID
	}
	if status.PersonaID == "" {
		status.PersonaID = personaID
	}
	return status, nil
}

func newGatheringRefService(
	store *testsupport.PostStore,
	reader postports.GatheringParticipationReader,
) *PostService {
	opts := []PostServiceOption{
		WithPublicationAdmission(
			testsupport.AllowPublicationRateGate{},
			testsupport.FixedPublicationSafetyGate{},
		),
	}
	if reader != nil {
		opts = append(opts, WithGatheringParticipationReader(reader))
	}
	return NewPostService(BindDataPorts(store), opts...)
}

func gatheringRefPublicationCommand(
	suffix string,
	gatheringRef string,
) SubmitPostPublicationCommand {
	return SubmitPostPublicationCommand{
		PublishIntentID: "intent-gathering-" + suffix,
		LocalDraftID:    "draft-gathering-" + suffix,
		AuthorID:        "persona-gathering",
		Content: postmodel.Post{
			ContentType:  "micro",
			Body:         "黄龙五彩池同行的回顾",
			Visibility:   "public",
			GatheringRef: gatheringRef,
		},
	}
}

func TestSubmitPostPublicationPersistsGatheringRefForActiveParticipant(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	reader := &gatheringParticipationReaderDouble{
		status: postports.GatheringParticipationStatus{
			GatheringID:        "gathering_huanglong_walk",
			PersonaID:          "persona-gathering",
			LifecycleStatus:    "published",
			ParticipationState: "active",
		},
	}
	service := newGatheringRefService(store, reader)

	command := gatheringRefPublicationCommand("active", "gathering_huanglong_walk")
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	if reader.calls != 1 {
		t.Fatalf("participation must be verified exactly once, got %d", reader.calls)
	}
	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("published post is missing: %s", receipt.PostID)
	}
	if stored.GatheringRef != "gathering_huanglong_walk" {
		t.Fatalf("verified gatheringRef must persist, got %q", stored.GatheringRef)
	}
	outbox := store.OutboxEvents()
	if len(outbox) == 0 {
		t.Fatal("publication must append an outbox event")
	}
	var payload map[string]any
	if err := json.Unmarshal(outbox[0].Payload, &payload); err != nil {
		t.Fatalf("decode outbox payload: %v", err)
	}
	payloadRef, _ := payload["gatheringRef"].(string)
	if payloadRef != "gathering_huanglong_walk" {
		t.Fatalf(
			"event payload must carry gatheringRef for downstream projections, got %q",
			payloadRef,
		)
	}
}

func TestSubmitPostPublicationRejectsGatheringRefWithoutActiveParticipation(t *testing.T) {
	for _, testCase := range []struct {
		name  string
		state string
	}{
		{name: "application pending is not participation", state: "application_pending"},
		{name: "closed participation lost access", state: "closed"},
		{name: "no participation at all", state: ""},
	} {
		t.Run(testCase.name, func(t *testing.T) {
			store := testsupport.NewPostStore(nil)
			reader := &gatheringParticipationReaderDouble{
				status: postports.GatheringParticipationStatus{
					GatheringID:        "gathering_huanglong_walk",
					PersonaID:          "persona-gathering",
					LifecycleStatus:    "published",
					ParticipationState: testCase.state,
				},
			}
			service := newGatheringRefService(store, reader)

			command := gatheringRefPublicationCommand(
				testCase.state+"-reject",
				"gathering_huanglong_walk",
			)
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
				"CONTENT.USER.gathering_participation_required",
			)
			if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
				t.Fatalf("rejected gatheringRef must not persist a Post: %+v", posts)
			}
		})
	}
}

func TestSubmitPostPublicationFailsClosedWhenParticipationReaderMissing(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	service := newGatheringRefService(store, nil)

	command := gatheringRefPublicationCommand("unwired", "gathering_huanglong_walk")
	_, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)

	requirePublicationErrorCode(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
	)
	if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
		t.Fatalf("unverified gatheringRef must not persist a Post: %+v", posts)
	}
}

func TestSubmitPostPublicationFailsClosedWhenCircleUnavailable(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	reader := &gatheringParticipationReaderDouble{
		err: fmt.Errorf("circle-service timeout"),
	}
	service := newGatheringRefService(store, reader)

	command := gatheringRefPublicationCommand("unavailable", "gathering_huanglong_walk")
	_, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)

	requirePublicationErrorCode(
		t,
		err,
		"CONTENT.SYSTEM.required_dependency_unavailable",
	)
	if posts, _ := store.ListAll(context.Background()); len(posts) != 0 {
		t.Fatalf("unavailable verification must not persist a Post: %+v", posts)
	}
}

func TestSubmitPostPublicationSkipsParticipationCheckWithoutGatheringRef(t *testing.T) {
	store := testsupport.NewPostStore(nil)
	reader := &gatheringParticipationReaderDouble{}
	service := newGatheringRefService(store, reader)

	command := gatheringRefPublicationCommand("plain", "")
	receipt, err := service.SubmitPostPublication(
		commandmeta.WithIdempotencyKey(context.Background(), command.PublishIntentID),
		command,
	)
	if err != nil {
		t.Fatal(err)
	}
	if reader.calls != 0 {
		t.Fatalf("plain post must not trigger participation reads, got %d", reader.calls)
	}
	stored, found := store.FindByID(context.Background(), receipt.PostID)
	if !found {
		t.Fatalf("published post is missing: %s", receipt.PostID)
	}
	if stored.GatheringRef != "" {
		t.Fatalf("plain post must not carry gatheringRef, got %q", stored.GatheringRef)
	}
}

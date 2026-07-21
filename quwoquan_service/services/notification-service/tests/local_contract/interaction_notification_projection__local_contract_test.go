package local_contract

import (
	"encoding/json"
	"testing"
	"time"

	"quwoquan_service/services/notification-service/internal/application"
)

// 互动与治理触发矩阵唯一真相源：
// specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md
// 本测试固定投影规则：接收者、type/source 映射、幂等键与全部不通知条件。

func contentEvent(t *testing.T, eventType, eventID string, payload map[string]any) application.InteractionStreamEvent {
	t.Helper()
	raw, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}
	return application.InteractionStreamEvent{
		Stream:     "events.content.test",
		MessageID:  "1-0",
		EventID:    eventID,
		EventType:  eventType,
		Values:     map[string]string{"eventId": eventID, "eventType": eventType},
		Payload:    raw,
		OccurredAt: time.Now().UTC(),
	}
}

func flatEvent(eventType, eventID string, values map[string]string) application.InteractionStreamEvent {
	merged := map[string]string{"eventId": eventID, "eventName": eventType}
	for key, value := range values {
		merged[key] = value
	}
	return application.InteractionStreamEvent{
		Stream:     "events.user.test",
		MessageID:  "1-0",
		EventID:    eventID,
		EventType:  eventType,
		Values:     merged,
		OccurredAt: time.Now().UTC(),
	}
}

func TestProjectionCoversSevenSourcesWithStableIdentity(t *testing.T) {
	cases := []struct {
		name        string
		event       application.InteractionStreamEvent
		recipient   string
		messageType string
		source      string
		targetType  string
		targetID    string
	}{
		{
			name: "comment on post notifies post author",
			event: contentEvent(t, "CommentCreated", "cmt-1:1", map[string]any{
				"commentId": "cmt-1", "postId": "post-1",
				"postAuthorId": "author-1", "authorId": "actor-1",
			}),
			recipient: "author-1", messageType: "content", source: "comment",
			targetType: "post", targetID: "post-1",
		},
		{
			name: "reply notifies replied user",
			event: contentEvent(t, "CommentCreated", "cmt-2:1", map[string]any{
				"commentId": "cmt-2", "postId": "post-1", "postAuthorId": "author-1",
				"authorId": "actor-1", "replyToUserId": "reply-target",
			}),
			recipient: "reply-target", messageType: "content", source: "comment",
			targetType: "post", targetID: "post-1",
		},
		{
			name: "pin notifies Comment author",
			event: contentEvent(t, "CommentPinChanged", "cmt-pin-1:2", map[string]any{
				"commentId": "cmt-pin-1", "postId": "post-1",
				"commentAuthorId": "comment-author-1", "operatorId": "post-author-1",
				"isPinned": true,
			}),
			recipient: "comment-author-1", messageType: "content", source: "comment_pin",
			targetType: "post", targetID: "post-1",
		},
		{
			name: "persona like notifies target author",
			event: contentEvent(t, "ContentReactionSet", "reaction:r-1:1", map[string]any{
				"reactionId": "r-1", "targetKind": "post", "targetId": "post-1",
				"targetAuthorId": "author-1", "actorDimension": "persona",
				"actorId": "actor-1", "reaction": "like",
			}),
			recipient: "author-1", messageType: "content", source: "reaction",
			targetType: "post", targetID: "post-1",
		},
		{
			name: "quoted publish notifies source author",
			event: contentEvent(t, "PostPublished", "evt-quote-1", map[string]any{
				"postId": "post-2", "authorId": "resharer-1",
				"sourcePostId": "post-1", "sourcePostAuthorId": "author-1",
			}),
			recipient: "author-1", messageType: "content", source: "post_quote",
			targetType: "post", targetID: "post-2",
		},
		{
			name: "resolved report notifies reporter",
			event: contentEvent(t, "content.report.resolved", "report-1:3", map[string]any{
				"reportId": "report-1", "reporterAccountId": "account-reporter-1",
				"targetType": "post", "targetId": "post-1", "resolution": "delete_content",
			}),
			recipient: "account-reporter-1", messageType: "content", source: "report_result",
			targetType: "report", targetID: "report-1",
		},
		{
			name: "dismissed report notifies reporter",
			event: contentEvent(t, "content.report.dismissed", "report-2:3", map[string]any{
				"reportId": "report-2", "reporterAccountId": "account-reporter-1",
				"targetType": "post", "targetId": "post-2",
			}),
			recipient: "account-reporter-1", messageType: "content", source: "report_result",
			targetType: "report", targetID: "report-2",
		},
		{
			name: "homepage claim review notifies requester",
			event: contentEvent(t, "HomepageClaimReviewed", "claim-1:2", map[string]any{
				"claimRequestId": "claim-1", "homepageId": "homepage-1",
				"requesterPersonaId": "requester-1", "status": "approved",
			}),
			recipient: "requester-1", messageType: "entity", source: "homepage_claim_result",
			targetType: "homepage", targetID: "homepage-1",
		},
		{
			name: "homepage status review notifies reporter",
			event: contentEvent(t, "HomepageStatusReportReviewed", "status-1:2", map[string]any{
				"reportId": "status-1", "homepageId": "homepage-1",
				"reporterPersonaId": "reporter-1", "status": "confirmed_offline",
			}),
			recipient: "reporter-1", messageType: "entity", source: "homepage_status_result",
			targetType: "homepage", targetID: "homepage-1",
		},
		{
			name: "follow notifies followed persona",
			event: flatEvent("PersonaFollowStateChanged", "follow-1", map[string]string{
				"pairId": "pair-1", "sourcePersonaId": "actor-1",
				"targetPersonaId": "author-1", "following": "true",
			}),
			recipient: "author-1", messageType: "social", source: "follow",
			targetType: "user", targetID: "actor-1",
		},
		{
			name: "greeting notifies target when allowed",
			event: flatEvent("GreetingRequestSent", "greeting:g-1:GreetingRequestSent", map[string]string{
				"id": "g-1", "requesterSubAccountId": "actor-1",
				"targetSubAccountId": "author-1", "targetAllowsStrangerGreeting": "true",
			}),
			recipient: "author-1", messageType: "social", source: "greeting",
			targetType: "greeting", targetID: "g-1",
		},
		{
			name: "circle join notifies circle owner",
			event: contentEvent(t, "CircleMembershipJoined", "m-1:CircleMembershipJoined:1", map[string]any{
				"id": "m-1", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "actor-1", "state": "active",
			}),
			recipient: "owner-1", messageType: "circle", source: "circle_member",
			targetType: "circle", targetID: "circle-1",
		},
		{
			name: "circle membership request notifies circle owner",
			event: contentEvent(t, "CircleMembershipRequested", "m-2:CircleMembershipRequested:1", map[string]any{
				"id": "m-2", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "actor-1", "state": "pending",
			}),
			recipient: "owner-1", messageType: "circle", source: "circle_member_request",
			targetType: "circle", targetID: "circle-1",
		},
		{
			name: "circle membership approval notifies applicant",
			event: contentEvent(t, "CircleMembershipApproved", "m-2:CircleMembershipApproved:2", map[string]any{
				"id": "m-2", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "actor-1", "state": "active",
			}),
			recipient: "actor-1", messageType: "circle", source: "circle_member_request",
			targetType: "circle", targetID: "circle-1",
		},
		{
			name: "circle membership rejection notifies applicant",
			event: contentEvent(t, "CircleMembershipRejected", "m-3:CircleMembershipRejected:2", map[string]any{
				"id": "m-3", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "actor-1", "state": "rejected",
			}),
			recipient: "actor-1", messageType: "circle", source: "circle_member_request",
			targetType: "circle", targetID: "circle-1",
		},
		{
			name: "group membership request notifies group owner",
			event: contentEvent(t, "CircleGroupMembershipRequested", "gm-1:Requested:1", map[string]any{
				"id": "gm-1", "groupId": "group-1", "circleId": "circle-1",
				"groupOwnerPersonaId": "owner-1", "personaId": "actor-1",
			}),
			recipient: "owner-1", messageType: "circle", source: "circle_group",
			targetType: "circleGroup", targetID: "group-1",
		},
		{
			name: "group membership approval notifies applicant",
			event: contentEvent(t, "CircleGroupMembershipActivated", "gm-1:Activated:2", map[string]any{
				"id": "gm-1", "groupId": "group-1", "circleId": "circle-1",
				"groupOwnerPersonaId": "owner-1", "personaId": "actor-1",
			}),
			recipient: "actor-1", messageType: "circle", source: "circle_group",
			targetType: "circleGroup", targetID: "group-1",
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			commands, err := application.ProjectInteractionNotification(testCase.event)
			if err != nil {
				t.Fatalf("projection failed: %v", err)
			}
			if len(commands) != 1 || commands[0] == nil {
				t.Fatalf("expected one notification command, got %+v", commands)
			}
			command := commands[0]
			wantKey := application.InteractionNotificationIdempotencyKey(
				testCase.event.EventType,
				testCase.event.EventID,
				command.UserID,
				command.Source,
				command.SourceID,
			)
			if command.IdempotencyKey != wantKey {
				t.Fatalf("idempotencyKey=%q want=%q", command.IdempotencyKey, wantKey)
			}
			if command.UserID != testCase.recipient {
				t.Fatalf("recipient=%q want=%q", command.UserID, testCase.recipient)
			}
			if command.MessageType != testCase.messageType || command.Source != testCase.source {
				t.Fatalf(
					"type/source=%q/%q want=%q/%q",
					command.MessageType, command.Source,
					testCase.messageType, testCase.source,
				)
			}
			if command.Target.TargetType != testCase.targetType ||
				command.Target.TargetID != testCase.targetID {
				t.Fatalf(
					"target=%q/%q want=%q/%q",
					command.Target.TargetType, command.Target.TargetID,
					testCase.targetType, testCase.targetID,
				)
			}
			if command.Title == "" || command.Summary == "" {
				t.Fatalf("title/summary must not be empty")
			}
		})
	}
}

func TestCommentCreatedFanoutUsesDistinctStableDeliveryIdentity(t *testing.T) {
	event := contentEvent(t, "CommentCreated", "cmt-fanout-1:1", map[string]any{
		"commentId":        "cmt-fanout-1",
		"postId":           "post-1",
		"postAuthorId":     "post-author-1",
		"authorId":         "actor-1",
		"replyToUserId":    "reply-target-1",
		"mentionedUserIds": []string{"reply-target-1", "mention-target-1", "actor-1"},
	})

	first, err := application.ProjectInteractionNotification(event)
	if err != nil {
		t.Fatalf("project Comment fan-out: %v", err)
	}
	second, err := application.ProjectInteractionNotification(event)
	if err != nil {
		t.Fatalf("replay Comment fan-out: %v", err)
	}
	if len(first) != 2 || len(second) != 2 {
		t.Fatalf("Comment fan-out commands first=%d replay=%d, want 2", len(first), len(second))
	}
	seenKeys := map[string]string{}
	for index, command := range first {
		if command == nil {
			t.Fatalf("Comment fan-out command %d is nil", index)
		}
		if previousRecipient, duplicate := seenKeys[command.IdempotencyKey]; duplicate {
			t.Fatalf(
				"Comment fan-out recipients %q and %q share idempotency key %q",
				previousRecipient,
				command.UserID,
				command.IdempotencyKey,
			)
		}
		seenKeys[command.IdempotencyKey] = command.UserID
		if command.IdempotencyKey != second[index].IdempotencyKey {
			t.Fatalf(
				"Comment fan-out replay key drifted for %s: %q vs %q",
				command.UserID,
				command.IdempotencyKey,
				second[index].IdempotencyKey,
			)
		}
	}
	if seenKeys[first[0].IdempotencyKey] == seenKeys[first[1].IdempotencyKey] {
		t.Fatalf("Comment fan-out did not preserve distinct recipients: %+v", first)
	}
}

func TestProjectionSkipsNonNotifiableEvents(t *testing.T) {
	cases := []struct {
		name  string
		event application.InteractionStreamEvent
	}{
		{
			name: "self comment",
			event: contentEvent(t, "CommentCreated", "cmt-3:1", map[string]any{
				"commentId": "cmt-3", "postId": "post-1",
				"postAuthorId": "actor-1", "authorId": "actor-1",
			}),
		},
		{
			name: "self reply",
			event: contentEvent(t, "CommentCreated", "cmt-4:1", map[string]any{
				"commentId": "cmt-4", "postId": "post-1", "postAuthorId": "author-1",
				"authorId": "actor-1", "replyToUserId": "actor-1",
			}),
		},
		{
			name: "reaction cleared",
			event: contentEvent(t, "ContentReactionCleared", "reaction:r-2:2", map[string]any{
				"reactionId": "r-2", "targetKind": "post", "targetId": "post-1",
				"actorDimension": "persona", "actorId": "actor-1", "reaction": "none",
			}),
		},
		{
			name: "self like",
			event: contentEvent(t, "ContentReactionSet", "reaction:r-3:1", map[string]any{
				"reactionId": "r-3", "targetKind": "post", "targetId": "post-1",
				"targetAuthorId": "actor-1", "actorDimension": "persona",
				"actorId": "actor-1", "reaction": "like",
			}),
		},
		{
			name: "device dimension like has no displayable actor",
			event: contentEvent(t, "ContentReactionSet", "reaction:r-4:1", map[string]any{
				"reactionId": "r-4", "targetKind": "post", "targetId": "post-1",
				"targetAuthorId": "author-1", "actorDimension": "device",
				"actorId": "device-1", "reaction": "like",
			}),
		},
		{
			name: "comment dislike never notifies",
			event: contentEvent(t, "ContentReactionSet", "reaction:r-5:1", map[string]any{
				"reactionId": "r-5", "targetKind": "comment", "targetId": "cmt-1",
				"targetAuthorId": "author-1", "actorDimension": "persona",
				"actorId": "actor-1", "reaction": "dislike",
			}),
		},
		{
			name: "plain publish without quote",
			event: contentEvent(t, "PostPublished", "evt-plain-1", map[string]any{
				"postId": "post-3", "authorId": "actor-1",
			}),
		},
		{
			name: "self quote",
			event: contentEvent(t, "PostPublished", "evt-selfquote-1", map[string]any{
				"postId": "post-4", "authorId": "actor-1",
				"sourcePostId": "post-1", "sourcePostAuthorId": "actor-1",
			}),
		},
		{
			name: "unfollow never notifies",
			event: flatEvent("PersonaFollowStateChanged", "follow-2", map[string]string{
				"pairId": "pair-2", "sourcePersonaId": "actor-1",
				"targetPersonaId": "author-1", "following": "false",
			}),
		},
		{
			name: "greeting blocked by stranger policy",
			event: flatEvent("GreetingRequestSent", "greeting:g-2:GreetingRequestSent", map[string]string{
				"id": "g-2", "requesterSubAccountId": "actor-1",
				"targetSubAccountId": "author-1", "targetAllowsStrangerGreeting": "false",
			}),
		},
		{
			name: "greeting cancel is not in the trigger matrix",
			event: flatEvent("GreetingRequestCancelled", "greeting:g-1:GreetingRequestCancelled", map[string]string{
				"id": "g-1", "requesterSubAccountId": "actor-1",
				"targetSubAccountId": "author-1", "targetAllowsStrangerGreeting": "true",
			}),
		},
		{
			name: "circle owner joins own circle",
			event: contentEvent(t, "CircleMembershipJoined", "m-2:CircleMembershipJoined:1", map[string]any{
				"id": "m-2", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "owner-1", "state": "active",
			}),
		},
		{
			name: "circle leave is not in the trigger matrix",
			event: contentEvent(t, "CircleMembershipLeft", "m-3:CircleMembershipLeft:2", map[string]any{
				"id": "m-3", "circleId": "circle-1",
				"circleOwnerPersonaId": "owner-1", "personaId": "actor-1", "state": "left",
			}),
		},
		{
			name: "group owner self activation",
			event: contentEvent(t, "CircleGroupMembershipActivated", "gm-2:Activated:1", map[string]any{
				"id": "gm-2", "groupId": "group-1", "circleId": "circle-1",
				"groupOwnerPersonaId": "owner-1", "personaId": "owner-1",
			}),
		},
		{
			name: "post lifecycle deletion is not an interaction",
			event: contentEvent(t, "PostDeleted", "evt-del-1", map[string]any{
				"postId": "post-1", "authorId": "actor-1",
			}),
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			commands, err := application.ProjectInteractionNotification(testCase.event)
			if err != nil {
				t.Fatalf("skip path must not error: %v", err)
			}
			if len(commands) != 0 {
				t.Fatalf("expected skip, got commands %+v", commands)
			}
		})
	}
}

func TestProjectionFailsClosedOnIncompletePayload(t *testing.T) {
	cases := []struct {
		name  string
		event application.InteractionStreamEvent
	}{
		{
			name: "comment payload missing identity",
			event: contentEvent(t, "CommentCreated", "cmt-bad:1", map[string]any{
				"postAuthorId": "author-1",
			}),
		},
		{
			name: "reaction payload missing identity",
			event: contentEvent(t, "ContentReactionSet", "reaction:bad:1", map[string]any{
				"targetAuthorId": "author-1", "reaction": "like",
			}),
		},
		{
			name: "follow event missing pair identity",
			event: flatEvent("PersonaFollowStateChanged", "follow-bad", map[string]string{
				"following": "true",
			}),
		},
		{
			name: "quoted publish missing post id",
			event: contentEvent(t, "PostPublished", "evt-quote-bad", map[string]any{
				"authorId": "resharer-1", "sourcePostId": "post-1",
				"sourcePostAuthorId": "author-1",
			}),
		},
		{
			name: "report result rejects persona-only recipient",
			event: contentEvent(t, "content.report.resolved", "report-bad:3", map[string]any{
				"reportId": "report-bad", "reporterId": "persona-only-reporter",
			}),
		},
	}
	for _, testCase := range cases {
		t.Run(testCase.name, func(t *testing.T) {
			command, err := application.ProjectInteractionNotification(testCase.event)
			if err == nil {
				t.Fatalf("expected structured failure, got command=%v", command)
			}
		})
	}
}

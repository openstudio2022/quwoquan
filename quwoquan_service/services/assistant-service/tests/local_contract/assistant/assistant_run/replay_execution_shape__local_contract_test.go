// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#req-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t1
package assistant_run_test

import (
	"strings"
	"testing"
	"time"

	simulator "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/replay"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// syntheticReplayShapeCatalog 是执行形状语义的最小合成目录：
// 一个 reactive 技能（带独占路由词）与一个 proactive-only 技能。
func syntheticReplayShapeCatalog() []skillpkg.Manifest {
	return []skillpkg.Manifest{
		{
			SkillID:      "replay_shape_reactive",
			DisplayName:  "回放形状响应技能",
			DomainID:     "domain.replay_shape",
			RoutingHints: []string{"回放形状响应"},
			Activation:   skillpkg.ActivationReactive,
		},
		{
			SkillID:     "replay_shape_proactive",
			DisplayName: "回放形状主动技能",
			DomainID:    "domain.replay_shape",
			Activation:  skillpkg.ActivationProactive,
		},
	}
}

func replayShapeRunner() simulator.Runner {
	return simulator.Runner{
		Now: func() time.Time {
			return time.Date(2026, 8, 2, 10, 0, 0, 0, time.UTC)
		},
		Catalog: syntheticReplayShapeCatalog(),
	}
}

func replayShapeCase(skillID string, triggerType string) assistant.ReplayCase {
	return assistant.ReplayCase{
		ReplayCaseID: "replay_shape_" + skillID + "_" + triggerType,
		Request: assistant.ReplayRequest{
			SessionID:   "asn_replay_shape",
			TurnID:      "atn_replay_shape",
			UserID:      "persona_replay_shape",
			InputText:   "回放形状响应的问题",
			SkillID:     skillID,
			DomainID:    "domain.replay_shape",
			TriggerType: triggerType,
		},
		FakeModelScript: []assistant.ReplayModelStep{
			{
				Stage: "reasoning",
				Text:  "该问题可直接回答。",
				StructuredDelta: map[string]any{
					"nextAction": "answer",
				},
				FinishReason: "stop",
			},
			{
				Stage:        "final",
				Text:         "已直接完成回答。",
				FinishReason: "stop",
			},
		},
		Expectations: assistant.ReplayExpectations{
			SelectedSkillID:              skillID,
			SelectedDomainID:             "domain.replay_shape",
			ExpectedToolNames:            []string{},
			ExpectedClarificationSlotIDs: []string{},
			ExpectedReferenceURLs:        []string{},
			FinalAnswerMode:              "full",
		},
	}
}

func trustedReplayShapeIdentity() *assistant.AssistantTriggerEnvelope {
	return &assistant.AssistantTriggerEnvelope{
		Kind:              "schedule",
		TriggerID:         "trg_replay_shape",
		OccurredAt:        time.Date(2026, 8, 2, 9, 30, 0, 0, time.UTC),
		SubscriptionRef:   "sks_replay_shape",
		Reason:            "subscription_due",
		DedupeKey:         "trg_replay_shape",
		DeliveryPolicyRef: "delivery.quiet_hours.default",
	}
}

// TestReplayRunnerFailsClosedOnExecutionShape 断言 Runner 的执行形状语义：
// reactive Case 必须经 production routing 命中期望技能；proactive Case 必须
// 携带完整受信 trigger identity，缺失或不完整一律 fail-closed。
func TestReplayRunnerFailsClosedOnExecutionShape(t *testing.T) {
	t.Parallel()
	runner := replayShapeRunner()
	tests := []struct {
		name        string
		mutate      func(*assistant.ReplayCase)
		wantErrPart string
	}{
		{
			name:   "reactive case routed by production router succeeds",
			mutate: func(replay *assistant.ReplayCase) {},
		},
		{
			name: "reactive input routed to another skill fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				replay.Request.InputText = "一个不含路由词的输入"
			},
			wantErrPart: "production router selected skill",
		},
		{
			name: "reactive case with trigger identity fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				replay.Request.TrustedTriggerIdentity = trustedReplayShapeIdentity()
			},
			wantErrPart: "must not carry a trusted trigger identity",
		},
		{
			name: "proactive case with trusted identity succeeds",
			mutate: func(replay *assistant.ReplayCase) {
				*replay = replayShapeCase("replay_shape_proactive", "proactive")
				replay.Request.TrustedTriggerIdentity = trustedReplayShapeIdentity()
			},
		},
		{
			name: "proactive case without identity fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				*replay = replayShapeCase("replay_shape_proactive", "proactive")
			},
			wantErrPart: "requires a trusted trigger identity",
		},
		{
			name: "proactive identity missing dedupe key fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				*replay = replayShapeCase("replay_shape_proactive", "proactive")
				identity := trustedReplayShapeIdentity()
				identity.DedupeKey = ""
				replay.Request.TrustedTriggerIdentity = identity
			},
			wantErrPart: "invalid trusted trigger identity",
		},
		{
			name: "proactive identity with unknown kind fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				*replay = replayShapeCase("replay_shape_proactive", "proactive")
				identity := trustedReplayShapeIdentity()
				identity.Kind = "not_a_trigger_kind"
				replay.Request.TrustedTriggerIdentity = identity
			},
			wantErrPart: "invalid trusted trigger identity",
		},
		{
			name: "proactive declaration on reactive-only skill fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				replay.Request.TriggerType = "proactive"
				replay.Request.TrustedTriggerIdentity = trustedReplayShapeIdentity()
			},
			wantErrPart: "does not accept proactive triggers",
		},
		{
			name: "reactive execution of proactive-only skill fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				*replay = replayShapeCase("replay_shape_proactive", "")
			},
			wantErrPart: "proactive-only and requires a trusted trigger identity",
		},
		{
			name: "unknown trigger type fails closed",
			mutate: func(replay *assistant.ReplayCase) {
				replay.Request.TriggerType = "webhook"
			},
			wantErrPart: "trigger type",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			replay := replayShapeCase("replay_shape_reactive", "")
			test.mutate(&replay)
			transcript, err := runner.Run(t.Context(), replay)
			if test.wantErrPart != "" {
				if err == nil || !strings.Contains(err.Error(), test.wantErrPart) {
					t.Fatalf("Run() error = %v, want containing %q", err, test.wantErrPart)
				}
				return
			}
			if err != nil {
				t.Fatalf("Run() error = %v", err)
			}
			if transcript.SelectedSkillID != replay.Expectations.SelectedSkillID ||
				transcript.FinalAnswerMode != "full" {
				t.Fatalf(
					"selected skill=%q finalAnswerMode=%q, want %q/full",
					transcript.SelectedSkillID,
					transcript.FinalAnswerMode,
					replay.Expectations.SelectedSkillID,
				)
			}
		})
	}
}

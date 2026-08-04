package orchestration

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// PreparedExecution is the immutable boundary between model inference and
// Adaptive Presentation. Both consumers must observe the same selected Skill
// and Context snapshot; Presentation must never resolve context a second time.
type PreparedExecution struct {
	SkillID             string
	PresentationProfile skillpkg.PresentationProfile
	ContextSnapshot     *skillcontext.Snapshot
	ConfirmedSlots      assistant.AssistantRunConfirmedSlots
}

type PreparedExecutionObserver func(PreparedExecution) error

// RunTurnWithPreparedExecution exposes the single immutable Skill/Context
// preparation used by model inference. It delegates to the same implementation
// as every existing AgentLoop entrypoint.
func (l *AgentLoop) RunTurnWithPreparedExecution(
	ctx context.Context,
	turn assistant.AssistantTurn,
	emit func(streaming.Envelope) error,
	observe PreparedExecutionObserver,
) ([]streaming.Envelope, *rtfailures.Failure, error) {
	return l.runTurnWithSinkAfterSeq(ctx, turn, 0, emit, observe)
}

func freezePreparedExecution(selection SkillSelection) (PreparedExecution, error) {
	skillID := strings.TrimSpace(selection.SkillID)
	if skillID == "" {
		return PreparedExecution{}, fmt.Errorf("prepared execution has no selected Skill")
	}
	prepared := PreparedExecution{
		SkillID:             skillID,
		PresentationProfile: freezePresentationProfile(selection.PresentationProfile),
	}
	if selection.ContextAssembly == nil {
		return prepared, nil
	}
	confirmedSlots, err := contextassembly.FreezeConfirmedSlots(
		selection.ContextAssembly.SlotState,
	)
	if err != nil {
		return PreparedExecution{}, err
	}
	prepared.ConfirmedSlots = confirmedSlots.Clone()
	if selection.ContextAssembly.SkillContextSnapshot == nil {
		return prepared, nil
	}
	raw, err := json.Marshal(selection.ContextAssembly.SkillContextSnapshot)
	if err != nil {
		return PreparedExecution{}, fmt.Errorf("freeze Skill context snapshot: %w", err)
	}
	var snapshot skillcontext.Snapshot
	if err := json.Unmarshal(raw, &snapshot); err != nil {
		return PreparedExecution{}, fmt.Errorf("freeze Skill context snapshot: %w", err)
	}
	if strings.TrimSpace(snapshot.SnapshotID) == "" {
		return PreparedExecution{}, fmt.Errorf("freeze Skill context snapshot: snapshotId is required")
	}
	prepared.ContextSnapshot = &snapshot
	return prepared, nil
}

func freezePresentationProfile(
	value skillpkg.PresentationProfile,
) skillpkg.PresentationProfile {
	return skillpkg.PresentationProfile{
		ProfileID:    strings.TrimSpace(value.ProfileID),
		IconToken:    strings.TrimSpace(value.IconToken),
		TemplateRefs: append([]string(nil), value.TemplateRefs...),
		AssetDigest:  strings.TrimSpace(value.AssetDigest),
	}
}

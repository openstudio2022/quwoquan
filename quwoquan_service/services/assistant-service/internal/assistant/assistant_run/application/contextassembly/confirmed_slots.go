package contextassembly

import (
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistantmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
)

// FreezeConfirmedSlots projects only explicit, canonical string confirmations
// from descriptor-driven SlotState. Inferred, stale, conflicted and missing
// values remain execution observations and never become session continuity.
func FreezeConfirmedSlots(
	state SlotState,
) (assistantmodel.AssistantRunConfirmedSlots, error) {
	values := make(map[string]string, len(state.Slots))
	for slotID, slot := range state.Slots {
		if slot.Status != assistantgenerated.SlotValueStatusConfirmed {
			continue
		}
		value, ok := slot.Value.(string)
		if !ok {
			return nil, fmt.Errorf(
				"confirmed slot %q is not a canonical string",
				strings.TrimSpace(slotID),
			)
		}
		values[slotID] = value
	}
	confirmed, err := assistantmodel.NewAssistantRunConfirmedSlots(values)
	if err != nil {
		return nil, fmt.Errorf("freeze confirmed slot state: %w", err)
	}
	return confirmed, nil
}

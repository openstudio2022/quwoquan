package persistence

import (
	"testing"

	relmodel "quwoquan_service/services/user-service/internal/domain/relationship/persona_relationship/model"
)

func TestClearedFollowDirections_EncodesBothBlockDirections(t *testing.T) {
	command := relmodel.Command{
		Kind:            relmodel.CommandBlock,
		SourcePersonaID: "persona-a",
		TargetPersonaID: "persona-b",
	}
	sourceCleared, targetCleared := clearedFollowDirections(
		command,
		[]relmodel.Direction{
			{
				SourcePersonaID: "persona-a",
				TargetPersonaID: "persona-b",
				Following:       true,
			},
			{
				SourcePersonaID: "persona-b",
				TargetPersonaID: "persona-a",
				Following:       true,
			},
		},
	)
	if !sourceCleared || !targetCleared {
		t.Fatalf(
			"expected both cleared directions, source=%v target=%v",
			sourceCleared,
			targetCleared,
		)
	}
}

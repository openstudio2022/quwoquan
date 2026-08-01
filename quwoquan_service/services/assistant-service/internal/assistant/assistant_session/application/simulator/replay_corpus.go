package simulator

import (
	"fmt"
	"os"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
)

const ReplayCasesPerSkill = skillpkg.MinimumReplayCasesPerSkill

type ReplayCorpus = skillpkg.ReplayCorpus
type ReplayCorpusAsset = skillpkg.ReplayCorpusAsset
type ReplayCorpusCase = skillpkg.ReplayCorpusCase

func LoadReplayCorpus(path string) (ReplayCorpus, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return ReplayCorpus{}, fmt.Errorf("read replay corpus: %w", err)
	}
	return skillpkg.DecodeReplayCorpus(raw)
}

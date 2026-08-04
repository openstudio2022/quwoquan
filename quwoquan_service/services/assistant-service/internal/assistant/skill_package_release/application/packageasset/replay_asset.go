package skill

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

const MinimumReplayCasesPerSkill = 10

type ReplayCorpus struct {
	Assets []ReplayCorpusAsset `json:"assets"`
}

type ReplayCorpusAsset struct {
	AssetID               string             `json:"assetId"`
	SkillID               string             `json:"skillId"`
	SkillProfileDigest    string             `json:"skillReleaseDigest"`
	EvaluationProfileRef  string             `json:"evaluationProfileRef"`
	EvaluationAssetDigest string             `json:"evaluationAssetDigest"`
	Cases                 []ReplayCorpusCase `json:"cases"`
}

type ReplayCorpusCase struct {
	CaseID              string `json:"caseId"`
	Input               string `json:"input"`
	Scenario            string `json:"scenario"`
	ClarificationSlotID string `json:"clarificationSlotId,omitempty"`
}

func DecodeReplayCorpus(raw []byte) (ReplayCorpus, error) {
	var corpus ReplayCorpus
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&corpus); err != nil {
		return ReplayCorpus{}, fmt.Errorf("decode replay corpus: %w", err)
	}
	if len(corpus.Assets) == 0 {
		return ReplayCorpus{}, fmt.Errorf("replay corpus has no assets")
	}
	return corpus, nil
}

func (corpus ReplayCorpus) ResolveAsset(
	assetRef string,
	skillID string,
) (ReplayCorpusAsset, AssetProof, error) {
	assetRef = strings.TrimSpace(assetRef)
	skillID = strings.TrimSpace(skillID)
	if assetRef == "" || skillID == "" {
		return ReplayCorpusAsset{}, AssetProof{}, fmt.Errorf(
			"replay asset ref and skill id are required",
		)
	}
	for _, asset := range corpus.Assets {
		if strings.TrimSpace(asset.AssetID) != assetRef {
			continue
		}
		if strings.TrimSpace(asset.SkillID) != skillID {
			return ReplayCorpusAsset{}, AssetProof{}, fmt.Errorf(
				"replay asset %q belongs to skill %q, want %q",
				assetRef,
				asset.SkillID,
				skillID,
			)
		}
		raw, err := json.Marshal(asset)
		if err != nil {
			return ReplayCorpusAsset{}, AssetProof{}, err
		}
		digest := sha256.Sum256(raw)
		return asset, AssetProof{
			ProfileID:   assetRef,
			AssetDigest: "sha256:" + hex.EncodeToString(digest[:]),
		}, nil
	}
	return ReplayCorpusAsset{}, AssetProof{}, fmt.Errorf(
		"replay asset %q is missing",
		assetRef,
	)
}

func (asset ReplayCorpusAsset) Validate(manifest Manifest) error {
	profileDigest, err := manifest.ResolvedProfileDigest()
	if err != nil {
		return err
	}
	evaluation, found := manifest.ResolvedAssetRefs["evaluation"]
	if !found {
		return fmt.Errorf(
			"skill %q has no resolved evaluation asset",
			manifest.SkillID,
		)
	}
	if strings.TrimSpace(asset.AssetID) == "" ||
		asset.AssetID != manifest.ReplayAssetRef ||
		asset.SkillID != manifest.SkillID ||
		asset.SkillProfileDigest != profileDigest ||
		asset.EvaluationProfileRef != manifest.EvaluationProfileRef ||
		asset.EvaluationAssetDigest != evaluation.AssetDigest {
		return fmt.Errorf(
			"replay asset %q is not bound to skill profile %q: declared %q expected %q",
			asset.AssetID,
			manifest.SkillID,
			asset.SkillProfileDigest,
			profileDigest,
		)
	}
	if len(asset.Cases) < MinimumReplayCasesPerSkill {
		return fmt.Errorf(
			"skill %q replay cases=%d, want at least %d",
			manifest.SkillID,
			len(asset.Cases),
			MinimumReplayCasesPerSkill,
		)
	}
	requiredScenarios := map[string]bool{
		"tool_selection":    false,
		"citation_boundary": false,
		"prompt_injection":  false,
		"failure_recovery":  false,
	}
	if manifest.SlotSchema.HasRequiredSlots() {
		requiredScenarios["slot_clarification"] = false
	} else {
		requiredScenarios["direct_answer"] = false
	}
	seenCaseIDs := map[string]bool{}
	seenInputs := map[string]bool{}
	for _, replayCase := range asset.Cases {
		caseID := strings.TrimSpace(replayCase.CaseID)
		input := strings.TrimSpace(replayCase.Input)
		scenario := strings.TrimSpace(replayCase.Scenario)
		if caseID == "" || input == "" || scenario == "" ||
			seenCaseIDs[caseID] || seenInputs[input] {
			return fmt.Errorf(
				"skill %q has invalid or duplicate replay case %q",
				manifest.SkillID,
				caseID,
			)
		}
		seenCaseIDs[caseID] = true
		seenInputs[input] = true
		if _, required := requiredScenarios[scenario]; required {
			requiredScenarios[scenario] = true
		}
	}
	for scenario, covered := range requiredScenarios {
		if !covered {
			return fmt.Errorf(
				"skill %q replay corpus misses %s",
				manifest.SkillID,
				scenario,
			)
		}
	}
	return nil
}

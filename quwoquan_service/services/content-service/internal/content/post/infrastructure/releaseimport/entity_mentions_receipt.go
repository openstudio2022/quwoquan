package releaseimport

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

type homepageImportProof struct {
	Schema                 string            `json:"schema"`
	Environment            string            `json:"env"`
	ReleaseID              string            `json:"releaseId"`
	SourceOwner            string            `json:"sourceOwner"`
	ManifestDigest         string            `json:"manifestDigest"`
	DryRun                 *bool             `json:"dryRun"`
	Expected               *int              `json:"expected"`
	Projected              *int              `json:"projected"`
	ProjectionVersion      int64             `json:"projectionVersion"`
	ClosureDigest          string            `json:"closureDigest"`
	EntityRefMappingDigest string            `json:"entityRefMappingDigest"`
	EntityRefToHomepageID  map[string]string `json:"entityRefToHomepageId"`
	Issues                 []json.RawMessage `json:"issues"`
}

type homepageCandidateProof struct {
	Schema   string `json:"schema"`
	Status   string `json:"status"`
	Identity struct {
		Environment    string `json:"environment"`
		ReleaseID      string `json:"releaseId"`
		SourceOwner    string `json:"sourceOwner"`
		ManifestDigest string `json:"manifestDigest"`
	} `json:"identity"`
	Counts *struct {
		Expected  int `json:"expected"`
		Projected int `json:"projected"`
	} `json:"counts"`
	ProjectionVersion      int64  `json:"projectionVersion"`
	ClosureDigest          string `json:"closureDigest"`
	EntityRefMappingDigest string `json:"entityRefMappingDigest"`
}

// LoadHomepageEntityMapping 只消费同一 exact candidate 认证过的 report 映射。
// dry-run 不读取裸 report、不生成 Homepage 身份，也不声称已解析导航。
func LoadHomepageEntityMapping(reportPath, candidatePath string, binding ReleaseBinding, environment string, dryRun bool, expectedRefs map[string]bool) (map[string]string, error) {
	if dryRun {
		if candidatePath != "" {
			return nil, fmt.Errorf("dry-run must not consume a homepage candidate mapping")
		}
		return nil, nil
	}
	if reportPath == "" || candidatePath == "" || strings.TrimSpace(environment) == "" {
		return nil, fmt.Errorf("homepage import report and exact candidate receipt require explicit paths and environment")
	}
	var report homepageImportProof
	if err := loadReleaseJSON(reportPath, &report); err != nil {
		return nil, fmt.Errorf("load homepage import report: %w", err)
	}
	var candidate homepageCandidateProof
	if err := loadReleaseJSON(candidatePath, &candidate); err != nil {
		return nil, fmt.Errorf("load homepage candidate receipt: %w", err)
	}
	identity := candidate.Identity
	if candidate.Schema != "quwoquan.homepage_release_candidate_receipt" || candidate.Status != "found" ||
		report.Schema != "quwoquan_service.homepage_import_report" || report.DryRun == nil || *report.DryRun ||
		identity.Environment != environment || report.Environment != environment ||
		identity.ReleaseID != binding.ReleaseID || report.ReleaseID != binding.ReleaseID ||
		identity.SourceOwner != binding.SourceOwner || report.SourceOwner != binding.SourceOwner ||
		identity.ManifestDigest != binding.ManifestDigest || report.ManifestDigest != binding.ManifestDigest {
		return nil, fmt.Errorf("homepage report/candidate exact identity mismatch")
	}
	if candidate.Counts == nil || report.Expected == nil || report.Projected == nil ||
		candidate.Counts.Expected != len(expectedRefs) || candidate.Counts.Projected != len(expectedRefs) ||
		*report.Expected != len(expectedRefs) || *report.Projected != len(expectedRefs) ||
		len(report.EntityRefToHomepageID) != len(expectedRefs) || len(report.Issues) != 0 {
		return nil, fmt.Errorf("homepage report/candidate entity closure mismatch")
	}
	if candidate.ProjectionVersion <= 0 || report.ProjectionVersion != candidate.ProjectionVersion ||
		!sha256Pattern.MatchString(candidate.ClosureDigest) || report.ClosureDigest != candidate.ClosureDigest {
		return nil, fmt.Errorf("homepage report/candidate projection closure drift")
	}
	keys := make([]string, 0, len(expectedRefs))
	seenIDs := make(map[string]bool, len(expectedRefs))
	for ref, id := range report.EntityRefToHomepageID {
		if !expectedRefs[ref] || strings.TrimSpace(id) == "" || strings.TrimSpace(id) != id || seenIDs[id] {
			return nil, fmt.Errorf("homepage mapping has missing, unexpected or duplicate identity")
		}
		keys = append(keys, ref)
		seenIDs[id] = true
	}
	sort.Strings(keys)
	// 与 Entity releaseMappingDigest 的既有 wire serialization 一致；不是 hp ID 算法。
	entries := make([]struct {
		EntityRef  string `json:"entityRef"`
		HomepageID string `json:"homepageId"`
	}, 0, len(keys))
	for _, ref := range keys {
		entries = append(entries, struct {
			EntityRef  string `json:"entityRef"`
			HomepageID string `json:"homepageId"`
		}{ref, report.EntityRefToHomepageID[ref]})
	}
	raw, err := json.Marshal(entries)
	if err != nil {
		return nil, err
	}
	sum := sha256.Sum256(raw)
	digest := "sha256:" + hex.EncodeToString(sum[:])
	if digest != candidate.EntityRefMappingDigest || digest != report.EntityRefMappingDigest {
		return nil, fmt.Errorf("homepage report/candidate mapping digest drift")
	}
	return report.EntityRefToHomepageID, nil
}

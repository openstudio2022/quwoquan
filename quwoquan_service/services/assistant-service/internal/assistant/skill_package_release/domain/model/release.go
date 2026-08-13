// Package model defines the immutable Skill Package release and active pointer.
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	RuntimeAPIVersion = "assistant-skill/v1"
	RuntimeVersion    = "1.0.0"

	StatusStaged  = "staged"
	StatusActive  = "active"
	StatusRetired = "retired"

	AssetManifest             = "manifest"
	AssetCatalog              = "catalog"
	AssetActivation           = "activation"
	AssetInput                = "input"
	AssetInputSchema          = "input_schema"
	AssetContext              = "context"
	AssetCapability           = "capability"
	AssetOrchestration        = "orchestration"
	AssetTrigger              = "trigger"
	AssetMemory               = "memory"
	AssetPresentation         = "presentation"
	AssetPresentationTemplate = "presentation_template"
	AssetEvaluation           = "evaluation"
	AssetPrompt               = "prompt"
	AssetReplay               = "replay"
)

var (
	ErrInvalidRelease           = errors.New("assistant skill package release is invalid")
	ErrDigestMismatch           = errors.New("assistant skill package digest mismatch")
	ErrAssetMismatch            = errors.New("assistant skill package asset digest mismatch")
	ErrAssetUnavailable         = errors.New("assistant skill package asset is unavailable")
	ErrRuntimeMismatch          = errors.New("assistant skill package runtime is incompatible")
	ErrSignatureInvalid         = errors.New("assistant skill package signature is invalid")
	ErrCapabilityDenied         = errors.New("assistant skill package capability is not granted")
	ErrReleaseNotFound          = errors.New("assistant skill package release not found")
	ErrActivationAbsent         = errors.New("assistant skill package activation not found")
	ErrRevisionConflict         = errors.New("assistant skill package activation revision conflict")
	ErrEvaluationReceiptInvalid = errors.New("assistant skill package evaluation receipt does not match the release")
)

// EvaluationConclusionPassed 是允许激活的唯一评测结论。
const EvaluationConclusionPassed = "passed"

// EvaluationReceipt 是轨迹回放评测通过凭据。激活必须携带对 exact package
// digest 与 exact replay corpus asset digest 的评测结论；任一 digest 与待
// 激活 release 不一致时激活 fail-closed。
type EvaluationReceipt struct {
	CorpusAssetID        string    `json:"corpusAssetId" bson:"corpusAssetId"`
	PackageReleaseDigest string    `json:"packageReleaseDigest" bson:"packageReleaseDigest"`
	ReplayAssetDigest    string    `json:"replayAssetDigest" bson:"replayAssetDigest"`
	EvaluatedAt          time.Time `json:"evaluatedAt" bson:"evaluatedAt"`
	Conclusion           string    `json:"conclusion" bson:"conclusion"`
}

// PassedEvaluationReceiptFor 为该 release 构造与 exact package/corpus digest
// 绑定的评测通过凭据。调用方必须先确证轨迹回放评测门禁在该 source 上通过；
// 该函数只做 digest 绑定，不替代评测本身。
func PassedEvaluationReceiptFor(
	release Release,
	evaluatedAt time.Time,
) (EvaluationReceipt, error) {
	for _, asset := range release.Assets {
		if asset.Kind != AssetReplay {
			continue
		}
		return EvaluationReceipt{
			CorpusAssetID:        asset.AssetID,
			PackageReleaseDigest: release.ReleaseDigest,
			ReplayAssetDigest:    asset.AssetDigest,
			EvaluatedAt:          evaluatedAt.UTC(),
			Conclusion:           EvaluationConclusionPassed,
		}, nil
	}
	return EvaluationReceipt{}, ErrEvaluationReceiptInvalid
}

// ValidateEvaluationReceipt 校验评测 receipt 与待激活 release 完全一致：
// package digest 精确匹配、replay asset 的 assetId 与 digest 精确匹配、
// 评测结论为 passed 且带评测时间。任何偏差都返回 ErrEvaluationReceiptInvalid。
func ValidateEvaluationReceipt(receipt EvaluationReceipt, release Release) error {
	receipt.CorpusAssetID = strings.TrimSpace(receipt.CorpusAssetID)
	receipt.PackageReleaseDigest = strings.TrimSpace(receipt.PackageReleaseDigest)
	receipt.ReplayAssetDigest = strings.TrimSpace(receipt.ReplayAssetDigest)
	receipt.Conclusion = strings.TrimSpace(receipt.Conclusion)
	if receipt.CorpusAssetID == "" ||
		!isDigest(receipt.PackageReleaseDigest) ||
		!isDigest(receipt.ReplayAssetDigest) ||
		receipt.EvaluatedAt.IsZero() ||
		receipt.Conclusion != EvaluationConclusionPassed {
		return ErrEvaluationReceiptInvalid
	}
	if receipt.PackageReleaseDigest != release.ReleaseDigest {
		return ErrEvaluationReceiptInvalid
	}
	for _, asset := range release.Assets {
		if asset.Kind != AssetReplay {
			continue
		}
		if receipt.CorpusAssetID == asset.AssetID &&
			receipt.ReplayAssetDigest == asset.AssetDigest {
			return nil
		}
	}
	return ErrEvaluationReceiptInvalid
}

type Asset struct {
	AssetID     string `json:"assetId" bson:"assetId"`
	Kind        string `json:"kind" bson:"kind"`
	Locator     string `json:"locator" bson:"locator"`
	AssetDigest string `json:"assetDigest" bson:"assetDigest"`
}

type RuntimeCompatibility struct {
	APIVersion            string `json:"apiVersion" bson:"apiVersion"`
	MinimumRuntimeVersion string `json:"minimumRuntimeVersion" bson:"minimumRuntimeVersion"`
	MaximumRuntimeVersion string `json:"maximumRuntimeVersion" bson:"maximumRuntimeVersion"`
}

type Provenance struct {
	SourceRepository string    `json:"sourceRepository" bson:"sourceRepository"`
	SourceRevision   string    `json:"sourceRevision" bson:"sourceRevision"`
	BuildID          string    `json:"buildId" bson:"buildId"`
	BuiltAt          time.Time `json:"builtAt" bson:"builtAt"`
}

type Signature struct {
	Algorithm string `json:"algorithm" bson:"algorithm"`
	KeyID     string `json:"keyId" bson:"keyId"`
	Value     string `json:"value" bson:"value"`
}

type CapabilityGrant struct {
	CapabilityID string `json:"capabilityId" bson:"capabilityId"`
	Scope        string `json:"scope" bson:"scope"`
}

type Release struct {
	PackageID            string               `json:"packageId" bson:"packageId"`
	PackageVersion       string               `json:"packageVersion" bson:"packageVersion"`
	ReleaseDigest        string               `json:"releaseDigest" bson:"releaseDigest"`
	Assets               []Asset              `json:"assets" bson:"assets"`
	RuntimeCompatibility RuntimeCompatibility `json:"runtimeCompatibility" bson:"runtimeCompatibility"`
	Provenance           Provenance           `json:"provenance" bson:"provenance"`
	Signature            Signature            `json:"signature" bson:"signature"`
	CapabilityGrants     []CapabilityGrant    `json:"capabilityGrants" bson:"capabilityGrants"`
	Status               string               `json:"status" bson:"status"`
	Revision             int                  `json:"revision" bson:"revision"`
	StagedAt             time.Time            `json:"stagedAt" bson:"stagedAt"`
	ActivatedAt          time.Time            `json:"activatedAt,omitempty" bson:"activatedAt,omitempty"`
}

type Activation struct {
	PackageID             string    `json:"packageId" bson:"packageId"`
	ActiveReleaseDigest   string    `json:"activeReleaseDigest" bson:"activeReleaseDigest"`
	PreviousReleaseDigest string    `json:"previousReleaseDigest,omitempty" bson:"previousReleaseDigest,omitempty"`
	Revision              int       `json:"revision" bson:"revision"`
	ActivatedAt           time.Time `json:"activatedAt" bson:"activatedAt"`
	ActivatedBy           string    `json:"activatedBy" bson:"activatedBy"`
}

func Stage(input Release, now time.Time) (Release, error) {
	normalized, err := Normalize(input)
	if err != nil {
		return Release{}, err
	}
	digest, err := Digest(normalized)
	if err != nil {
		return Release{}, err
	}
	if normalized.ReleaseDigest != digest {
		return Release{}, ErrDigestMismatch
	}
	normalized.Status = StatusStaged
	normalized.Revision = 1
	normalized.StagedAt = now.UTC()
	normalized.ActivatedAt = time.Time{}
	return normalized, nil
}

// Normalize validates and canonicalizes every field covered by ReleaseDigest.
func Normalize(input Release) (Release, error) {
	input.PackageID = strings.TrimSpace(input.PackageID)
	input.PackageVersion = strings.TrimSpace(input.PackageVersion)
	input.ReleaseDigest = strings.TrimSpace(input.ReleaseDigest)
	input.RuntimeCompatibility.APIVersion = strings.TrimSpace(input.RuntimeCompatibility.APIVersion)
	input.RuntimeCompatibility.MinimumRuntimeVersion = strings.TrimSpace(input.RuntimeCompatibility.MinimumRuntimeVersion)
	input.RuntimeCompatibility.MaximumRuntimeVersion = strings.TrimSpace(input.RuntimeCompatibility.MaximumRuntimeVersion)
	input.Provenance.SourceRepository = strings.TrimSpace(input.Provenance.SourceRepository)
	input.Provenance.SourceRevision = strings.TrimSpace(input.Provenance.SourceRevision)
	input.Provenance.BuildID = strings.TrimSpace(input.Provenance.BuildID)
	input.Signature.Algorithm = strings.TrimSpace(input.Signature.Algorithm)
	input.Signature.KeyID = strings.TrimSpace(input.Signature.KeyID)
	input.Signature.Value = strings.TrimSpace(input.Signature.Value)
	if input.PackageID == "" || !isSemver(input.PackageVersion) ||
		!isDigest(input.ReleaseDigest) ||
		input.RuntimeCompatibility.APIVersion == "" ||
		!isSemver(input.RuntimeCompatibility.MinimumRuntimeVersion) ||
		!isSemver(input.RuntimeCompatibility.MaximumRuntimeVersion) ||
		compareSemver(input.RuntimeCompatibility.MinimumRuntimeVersion, input.RuntimeCompatibility.MaximumRuntimeVersion) > 0 ||
		input.Provenance.SourceRepository == "" ||
		input.Provenance.SourceRevision == "" ||
		input.Provenance.BuildID == "" ||
		input.Provenance.BuiltAt.IsZero() ||
		input.Signature.Algorithm != "ed25519" ||
		input.Signature.KeyID == "" ||
		input.Signature.Value == "" ||
		len(input.Assets) == 0 || len(input.Assets) > 512 ||
		len(input.CapabilityGrants) == 0 || len(input.CapabilityGrants) > 256 {
		return Release{}, ErrInvalidRelease
	}

	requiredKinds := map[string]bool{
		AssetManifest: false, AssetCatalog: false, AssetActivation: false,
		AssetInput: false, AssetInputSchema: false, AssetContext: false, AssetCapability: false,
		AssetOrchestration: false, AssetTrigger: false, AssetMemory: false,
		AssetPresentation: false, AssetPresentationTemplate: false,
		AssetEvaluation: false, AssetPrompt: false,
		AssetReplay: false,
	}
	assetIDs := make(map[string]struct{}, len(input.Assets))
	assets := append([]Asset(nil), input.Assets...)
	for index := range assets {
		asset := &assets[index]
		asset.AssetID = strings.TrimSpace(asset.AssetID)
		asset.Kind = strings.TrimSpace(asset.Kind)
		asset.Locator = strings.TrimSpace(asset.Locator)
		asset.AssetDigest = strings.TrimSpace(asset.AssetDigest)
		if asset.AssetID == "" || asset.Locator == "" || !isDigest(asset.AssetDigest) {
			return Release{}, ErrInvalidRelease
		}
		if _, duplicate := assetIDs[asset.AssetID]; duplicate {
			return Release{}, ErrInvalidRelease
		}
		if _, supported := requiredKinds[asset.Kind]; !supported {
			return Release{}, ErrInvalidRelease
		}
		assetIDs[asset.AssetID] = struct{}{}
		requiredKinds[asset.Kind] = true
	}
	for _, present := range requiredKinds {
		if !present {
			return Release{}, ErrInvalidRelease
		}
	}
	sort.Slice(assets, func(left, right int) bool {
		return assets[left].AssetID < assets[right].AssetID
	})

	grants := append([]CapabilityGrant(nil), input.CapabilityGrants...)
	grantKeys := make(map[string]struct{}, len(grants))
	for index := range grants {
		grant := &grants[index]
		grant.CapabilityID = strings.TrimSpace(grant.CapabilityID)
		grant.Scope = strings.TrimSpace(grant.Scope)
		key := grant.CapabilityID + "\x00" + grant.Scope
		if !isCapabilityID(grant.CapabilityID) || grant.Scope == "" {
			return Release{}, ErrInvalidRelease
		}
		if _, duplicate := grantKeys[key]; duplicate {
			return Release{}, ErrInvalidRelease
		}
		grantKeys[key] = struct{}{}
	}
	sort.Slice(grants, func(left, right int) bool {
		if grants[left].CapabilityID == grants[right].CapabilityID {
			return grants[left].Scope < grants[right].Scope
		}
		return grants[left].CapabilityID < grants[right].CapabilityID
	})
	input.Assets = assets
	input.CapabilityGrants = grants
	input.Provenance.BuiltAt = input.Provenance.BuiltAt.UTC()
	return input, nil
}

func Digest(input Release) (string, error) {
	normalized, err := Normalize(input)
	if err != nil {
		return "", err
	}
	payload := struct {
		PackageID            string               `json:"packageId"`
		PackageVersion       string               `json:"packageVersion"`
		Assets               []Asset              `json:"assets"`
		RuntimeCompatibility RuntimeCompatibility `json:"runtimeCompatibility"`
		Provenance           Provenance           `json:"provenance"`
		SignatureAlgorithm   string               `json:"signatureAlgorithm"`
		SignatureKeyID       string               `json:"signatureKeyId"`
		CapabilityGrants     []CapabilityGrant    `json:"capabilityGrants"`
	}{
		PackageID:            normalized.PackageID,
		PackageVersion:       normalized.PackageVersion,
		Assets:               normalized.Assets,
		RuntimeCompatibility: normalized.RuntimeCompatibility,
		Provenance:           normalized.Provenance,
		SignatureAlgorithm:   normalized.Signature.Algorithm,
		SignatureKeyID:       normalized.Signature.KeyID,
		CapabilityGrants:     normalized.CapabilityGrants,
	}
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", ErrInvalidRelease
	}
	sum := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}

func RuntimeCompatible(
	compatibility RuntimeCompatibility,
	apiVersion string,
	runtimeVersion string,
) bool {
	apiVersion = strings.TrimSpace(apiVersion)
	runtimeVersion = strings.TrimSpace(runtimeVersion)
	return apiVersion != "" &&
		apiVersion == compatibility.APIVersion &&
		isSemver(runtimeVersion) &&
		isSemver(compatibility.MinimumRuntimeVersion) &&
		isSemver(compatibility.MaximumRuntimeVersion) &&
		compareSemver(runtimeVersion, compatibility.MinimumRuntimeVersion) >= 0 &&
		compareSemver(runtimeVersion, compatibility.MaximumRuntimeVersion) <= 0
}

func isDigest(value string) bool {
	if len(value) != len("sha256:")+sha256.Size*2 || !strings.HasPrefix(value, "sha256:") {
		return false
	}
	raw := strings.TrimPrefix(value, "sha256:")
	if raw != strings.ToLower(raw) {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}

func isSemver(value string) bool {
	parts := strings.Split(value, ".")
	if len(parts) != 3 {
		return false
	}
	for _, part := range parts {
		if part == "" || (len(part) > 1 && part[0] == '0') {
			return false
		}
		if _, err := strconv.Atoi(part); err != nil {
			return false
		}
	}
	return true
}

func compareSemver(left string, right string) int {
	leftParts := strings.Split(left, ".")
	rightParts := strings.Split(right, ".")
	for index := 0; index < 3; index++ {
		leftValue, _ := strconv.Atoi(leftParts[index])
		rightValue, _ := strconv.Atoi(rightParts[index])
		if leftValue < rightValue {
			return -1
		}
		if leftValue > rightValue {
			return 1
		}
	}
	return 0
}

func isCapabilityID(value string) bool {
	parts := strings.Split(value, ".")
	if len(parts) < 2 {
		return false
	}
	for _, part := range parts {
		if part == "" {
			return false
		}
		for _, current := range part {
			if (current >= 'a' && current <= 'z') ||
				(current >= '0' && current <= '9') ||
				current == '_' {
				continue
			}
			return false
		}
	}
	return true
}

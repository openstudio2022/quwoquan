package public

import (
	"context"
	rt "quwoquan_service/runtime/search"
	"strings"
	"time"
)

// ReleaseBindings只读取部署受管代际；调用方不能提交任意schema/provider选择。
type ReleaseBindings interface {
	BindingFor(context.Context, rt.ReleaseCandidateBinding, string) (rt.ReleaseQueryPreparationBinding, error)
}
type RecommendationReadinessReader interface {
	ReadRecommendationProof(context.Context, rt.ReleaseQueryPreparationBinding, string) (rt.ReleaseQueryReadinessProof, error)
}
type OwnerClosureReader interface {
	VerifyOwnerClosures(context.Context, rt.ReleaseCandidateBinding) error
}
type GenerationProtection interface {
	VerifyHeld(context.Context, rt.ReleaseCandidateBinding, time.Time) error
}
type RequiredQueryEvaluator struct {
	sources        ReleaseSourceQueries
	search         SearchPreparationPort
	recommendation RecommendationReadinessReader
	bindings       ReleaseBindings
	owners         OwnerClosureReader
	protection     GenerationProtection
	now            func() time.Time
}

func NewRequiredQueryEvaluator(sources ReleaseSourceQueries, search SearchPreparationPort, recommendation RecommendationReadinessReader, bindings ReleaseBindings, owners OwnerClosureReader, protection GenerationProtection, clock func() time.Time) (*RequiredQueryEvaluator, error) {
	if sources == nil || search == nil || recommendation == nil || bindings == nil || owners == nil || protection == nil || clock == nil {
		return nil, ErrReleaseQueryNotReady
	}
	return &RequiredQueryEvaluator{sources, search, recommendation, bindings, owners, protection, clock}, nil
}
func (e *RequiredQueryEvaluator) VerifyRequiredQueries(ctx context.Context, release rt.ReleaseCandidateBinding) error {
	// 只收紧现役上限；源读取、证明与保护共享入口预算，绝不重新起算。
	deadline := e.now().Add(10 * time.Second)
	if parentDeadline, ok := ctx.Deadline(); ok && parentDeadline.Before(deadline) {
		deadline = parentDeadline
	}
	checkBudget := func() error {
		if ctx.Err() != nil || !e.now().Before(deadline) {
			return ErrReleaseQueryNotReady
		}
		return nil
	}
	if err := checkBudget(); err != nil {
		return err
	}
	if err := e.owners.VerifyOwnerClosures(ctx, release); err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	creator, err := e.sources.ReadCreatorCandidate(ctx, release)
	if err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	post, err := e.sources.ReadPostCandidate(ctx, release)
	if err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	homepage, err := e.sources.ReadHomepageCandidate(ctx, release)
	if err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	for _, source := range []rt.SearchReleaseCandidateSnapshot{{Kind: "creator", Creator: &creator}, {Kind: "post", Post: &post}, {Kind: "homepage", Homepage: &homepage}} {
		binding, err := e.bindings.BindingFor(ctx, release, source.Kind+"_search")
		if err != nil {
			return err
		}
		if err := checkBudget(); err != nil {
			return err
		}
		proof, err := e.search.ReadSearchProof(ctx, binding, source.SnapshotDigest())
		if err != nil {
			return err
		}
		if err := checkBudget(); err != nil {
			return err
		}
		if proof.Validate(binding, source) != nil {
			return ErrReleaseQueryInvalid
		}
		if err := validateConsumedProofTime(proof, e.now(), deadline); err != nil {
			return err
		}
	}
	if err := checkBudget(); err != nil {
		return err
	}
	binding, err := e.bindings.BindingFor(ctx, release, "recommendation")
	if err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	proof, err := e.recommendation.ReadRecommendationProof(ctx, binding, post.SnapshotDigest)
	if err != nil {
		return err
	}
	if err := checkBudget(); err != nil {
		return err
	}
	if err := validateConsumedProofTime(proof, e.now(), deadline); err != nil {
		return err
	}
	digest, err := rt.CreatorCanonicalDigest(proof, "proofDigest")
	if err != nil || digest != proof.ProofDigest || proof.Binding != binding || proof.SourceClosureDigest != post.SourceClosureDigest || proof.SnapshotDigest != post.SnapshotDigest || proof.ObjectSetDigest != post.ObjectSetDigest || proof.PremiumAdmissionDigest == nil || proof.PremiumObjectSetDigest == nil {
		return ErrReleaseQueryInvalid
	}
	classes := map[string]bool{"home": true, "premium": true, "required_detail": true}
	for _, row := range proof.QueryClasses {
		if !classes[row.QueryClass] || row.DocumentsDigest == "" || row.ObjectSetDigest == "" {
			return ErrReleaseQueryInvalid
		}
		expectedSet := post.ObjectSetDigest
		if row.QueryClass == "premium" {
			expectedSet = *proof.PremiumObjectSetDigest
		}
		if row.ObjectSetDigest != expectedSet {
			return ErrReleaseQueryInvalid
		}
		delete(classes, row.QueryClass)
	}
	if len(classes) != 0 {
		return ErrReleaseQueryNotReady
	}
	if err := checkBudget(); err != nil {
		return err
	}
	if err := e.protection.VerifyHeld(ctx, release, deadline); err != nil {
		return err
	}
	return checkBudget()
}

// 无候选时钟容差authority时不借用JWT skew。此处仅验证必要条件，
// 不替代获准时间policy、持续安全保护或提交余量authority。
func validateConsumedProofTime(proof rt.ReleaseQueryReadinessProof, now, deadline time.Time) error {
	verified, err := time.Parse(time.RFC3339Nano, proof.VerifiedAt)
	if err != nil || !strings.HasSuffix(proof.VerifiedAt, "Z") || verified.After(now) || proof.CheckpointVersion <= 0 {
		return ErrReleaseQueryInvalid
	}
	until, err := time.Parse(time.RFC3339Nano, proof.ValidUntil)
	if err != nil || !strings.HasSuffix(proof.ValidUntil, "Z") {
		return ErrReleaseQueryInvalid
	}
	if !until.After(now) {
		return ErrReleaseQueryNotReady
	}
	if !until.After(verified) {
		return ErrReleaseQueryInvalid
	}
	if !until.After(deadline) {
		return ErrReleaseQueryNotReady
	}
	return nil
}

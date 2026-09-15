package application

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	rt "quwoquan_service/runtime/search"
	"quwoquan_service/services/search-service/internal/search/search_release_preparation/domain"
	"strings"
	"time"
)

type Service struct {
	store                   domain.Store
	projection              domain.Projection
	environment, generation string
	now                     func() time.Time
}

func NewService(store domain.Store, projection domain.Projection, environment, generation string, clock func() time.Time) (*Service, error) {
	if store == nil || projection == nil || clock == nil || environment == "" || generation == "" {
		return nil, domain.ErrInvalid
	}
	return &Service{store, projection, environment, generation, clock}, nil
}
func (s *Service) Prepare(ctx context.Context, c domain.Command, principal string) (domain.View, error) {
	if principal != "content-service" || c.ExpectedVersion < 0 || strings.TrimSpace(c.IdempotencyKey) == "" || len(c.IdempotencyKey) > 128 || c.Binding.Release != c.Snapshot.Release() || c.Binding.Slice != c.Snapshot.Kind+"_search" {
		return domain.View{}, domain.ErrInvalid
	}
	if err := c.Binding.Validate(s.environment, s.generation); err != nil {
		return domain.View{}, fmt.Errorf("%w: %v", domain.ErrInvalid, err)
	}
	if err := c.Snapshot.Validate(); err != nil {
		return domain.View{}, fmt.Errorf("%w: %v", domain.ErrInvalid, err)
	}
	key, _ := rt.CreatorCanonicalDigest([]string{principal, c.IdempotencyKey}, "")
	digest, _ := rt.CreatorCanonicalDigest(c, "")
	if view, found, err := s.store.Receipt(ctx, c.Binding.ID(), key, digest); err != nil || found {
		return view, err
	}
	state, err := s.store.Load(ctx, c.Binding.ID())
	if errors.Is(err, domain.ErrNotFound) {
		if c.ExpectedVersion != 0 {
			return domain.View{}, domain.ErrConflict
		}
		state = domain.NewState(c, s.now().UTC())
		if err = s.store.Create(ctx, state); err != nil {
			return domain.View{}, err
		}
	} else if err != nil {
		return domain.View{}, err
	}
	if state.Snapshot.SnapshotDigest() != c.Snapshot.SnapshotDigest() {
		return domain.View{}, domain.ErrConflict
	}
	if state.Status == "completed" || state.Status == "failed" {
		return state.View(), nil
	}
	expected := c.ExpectedVersion
	if expected == 0 {
		expected = 1
	}
	now := s.now().UTC()
	until := now.Add(30 * time.Second)
	if deadline, ok := ctx.Deadline(); ok && deadline.Before(until) {
		until = deadline
	}
	random := make([]byte, 32)
	if _, err = rand.Read(random); err != nil {
		return domain.View{}, domain.ErrUnavailable
	}
	token := hex.EncodeToString(random)
	if err = state.Claim(expected, token, now, until); err != nil {
		return domain.View{}, err
	}
	if err = s.store.Claim(ctx, state, expected, now); err != nil {
		return domain.View{}, err
	}
	claimedVersion := state.Version
	verified, prepareErr := s.projection.Prepare(ctx, state.Binding, state.Snapshot)
	state.VerifiedObjectIDs = verified
	var proof *rt.ReleaseQueryReadinessProof
	failure := "provider_unavailable"
	if prepareErr == nil {
		classes, verifyErr := s.projection.Verify(ctx, state.Binding, state.Snapshot)
		prepareErr = verifyErr
		if verifyErr == nil {
			if len(classes) == 0 {
				return domain.View{}, domain.ErrUnavailable
			}
			proof = &rt.ReleaseQueryReadinessProof{Binding: state.Binding, SourceClosureDigest: state.Snapshot.SourceClosureDigest(), ObjectSetDigest: state.Snapshot.ObjectSetDigest(), SnapshotDigest: state.Snapshot.SnapshotDigest(), DocumentsDigest: classes[0].DocumentsDigest, CheckpointVersion: state.Version + 1, QueryClasses: classes, VerifiedAt: s.now().UTC().Format(time.RFC3339Nano), ValidUntil: s.now().UTC().Add(30 * time.Second).Format(time.RFC3339Nano)}
			if err = proof.Seal(); err != nil {
				return domain.View{}, domain.ErrUnavailable
			}
			if err = proof.Validate(state.Binding, state.Snapshot); err != nil {
				return domain.View{}, domain.ErrInvalid
			}
		}
	}
	if errors.Is(prepareErr, domain.ErrInvalid) {
		failure = "source_invalid"
	}
	if errors.Is(prepareErr, domain.ErrConflict) || errors.Is(prepareErr, rt.ErrCreatorProjectionConflict) {
		failure = "projection_conflict"
	}
	now = s.now().UTC()
	if !state.CanCommit(token, now) {
		return domain.View{}, domain.ErrConflict
	}
	state.Finish(proof, failure, now)
	if err = s.store.Commit(ctx, state, claimedVersion, token, key, digest, now); err != nil {
		return domain.View{}, err
	}
	return state.View(), nil
}

// ReconcileRelease只读三slice已存在的冻结源及实际Provider证明，绝不创建/推进准备。
func (s *Service) ReconcileRelease(ctx context.Context, release rt.ReleaseCandidateBinding, schema string) (string, error) {
	proofs := []rt.ReleaseQueryReadinessProof{}
	for _, slice := range []string{"creator_search", "post_search", "homepage_search"} {
		binding := rt.ReleaseQueryPreparationBinding{Release: release, Slice: slice, ProviderBindingGeneration: s.generation, SchemaGeneration: schema}
		state, err := s.store.Load(ctx, binding.ID())
		if err != nil {
			return "", err
		}
		if state.Status != "completed" || state.Binding != binding {
			return "", domain.ErrConflict
		}
		view, err := s.Read(ctx, domain.Query{Binding: binding, SnapshotDigest: state.Snapshot.SnapshotDigest()})
		if err != nil {
			return "", err
		}
		if view.Proof == nil {
			return "", domain.ErrUnavailable
		}
		proofs = append(proofs, *view.Proof)
	}
	return rt.CreatorCanonicalDigest(proofs, "")
}

func (s *Service) Read(ctx context.Context, q domain.Query) (domain.View, error) {
	if err := q.Binding.Validate(s.environment, s.generation); err != nil {
		return domain.View{}, domain.ErrInvalid
	}
	state, err := s.store.Load(ctx, q.Binding.ID())
	if err != nil {
		return domain.View{}, err
	}
	if state.Snapshot.SnapshotDigest() != q.SnapshotDigest {
		return domain.View{}, domain.ErrConflict
	}
	if state.Status == "completed" {
		if state.Proof == nil || state.Proof.Validate(state.Binding, state.Snapshot) != nil {
			return domain.View{}, domain.ErrConflict
		}
		digest, err := s.projection.Verify(ctx, state.Binding, state.Snapshot)
		if err != nil {
			return domain.View{}, err
		}
		if len(digest) != len(state.Proof.QueryClasses) {
			return domain.View{}, domain.ErrConflict
		}
		for i, row := range digest {
			if row != state.Proof.QueryClasses[i] {
				return domain.View{}, domain.ErrConflict
			}
		}
		// query仅从原completed与实际Provider派生当前短窗口证明，不更新checkpoint。
		refreshed := *state.Proof
		refreshed.VerifiedAt = s.now().UTC().Format(time.RFC3339Nano)
		refreshed.ValidUntil = s.now().UTC().Add(30 * time.Second).Format(time.RFC3339Nano)
		if err := refreshed.Seal(); err != nil {
			return domain.View{}, err
		}
		state.Proof = &refreshed
	}
	return state.View(), nil
}

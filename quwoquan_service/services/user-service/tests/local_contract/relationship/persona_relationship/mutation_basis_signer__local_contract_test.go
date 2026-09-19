// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/follow-relationship/spec.md#gwt-006
package local_contract

import (
	"errors"
	"strings"
	"testing"
	"time"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
	relationshippersistence "quwoquan_service/services/user-service/internal/relationship/persona_relationship/infrastructure/persistence"
)

const (
	basisTestAudience = "user-service.alpha"
	basisTestKeyID    = "basis-key-1"
)

func newBasisSigner(t *testing.T, now func() time.Time) *relationshippersistence.MutationBasisSigner {
	t.Helper()
	signer, err := relationshippersistence.NewMutationBasisSigner(
		basisTestAudience,
		basisTestKeyID,
		[]relationshippersistence.MutationBasisKey{
			{ID: basisTestKeyID, Material: []byte(strings.Repeat("k", 32))},
		},
	)
	if err != nil {
		t.Fatalf("NewMutationBasisSigner error = %v", err)
	}
	return signer.WithClock(now)
}

func followCommand(source, target string, expectedVersion int64) relmodel.Command {
	return relmodel.Command{
		Kind:            relmodel.CommandFollow,
		SourcePersonaID: source,
		TargetPersonaID: target,
		ExpectedVersion: &expectedVersion,
	}
}

func TestMutationBasisRejectsForgedAndSwappedClaims(t *testing.T) {
	t.Parallel()

	const (
		actor  = "basis-actor"
		target = "basis-target"
		pairID = "basis-pair"
	)
	issuedAt := time.Date(2026, 9, 18, 0, 0, 0, 0, time.UTC)
	signer := newBasisSigner(t, func() time.Time { return issuedAt })
	token, err := signer.Issue(relationshipapp.MutationBasisClaims{
		ActorPersonaID:  actor,
		TargetPersonaID: target,
		TargetKind:      "persona",
		PairID:          pairID,
		ExpectedVersion: 7,
		AllowedActions:  []relmodel.CommandKind{relmodel.CommandFollow, relmodel.CommandUnfollow},
	})
	if err != nil {
		t.Fatalf("Issue error = %v", err)
	}

	if _, err := signer.Verify(token, followCommand(actor, target, 7), pairID); err != nil {
		t.Fatalf("legitimate basis must verify, got %v", err)
	}

	t.Run("swapping actor, target, pair or version invalidates the basis", func(t *testing.T) {
		cases := map[string]struct {
			command relmodel.Command
			pairID  string
		}{
			"other actor":      {followCommand("basis-other-actor", target, 7), pairID},
			"other target":     {followCommand(actor, "basis-other-target", 7), pairID},
			"other pair":       {followCommand(actor, target, 7), "basis-other-pair"},
			"other version":    {followCommand(actor, target, 8), pairID},
			"action not given": {blockCommandFor(actor, target), pairID},
		}
		for name, testCase := range cases {
			if _, err := signer.Verify(token, testCase.command, testCase.pairID); !errors.Is(err, relationshippersistence.ErrBasisInvalid) {
				t.Fatalf("%s error = %v, want ErrBasisInvalid", name, err)
			}
		}
	})

	t.Run("tampered payload or signature invalidates the basis", func(t *testing.T) {
		parts := strings.Split(token, ".")
		for name, tampered := range map[string]string{
			"unknown key":     "basis-key-unknown." + parts[1] + "." + parts[2],
			"broken payload":  parts[0] + ".not-base64!." + parts[2],
			"wrong signature": parts[0] + "." + parts[1] + "." + parts[2][:len(parts[2])-2] + "AA",
			"missing part":    parts[0] + "." + parts[1],
		} {
			if _, err := signer.Verify(tampered, followCommand(actor, target, 7), pairID); !errors.Is(err, relationshippersistence.ErrBasisInvalid) {
				t.Fatalf("%s error = %v, want ErrBasisInvalid", name, err)
			}
		}
		if _, err := signer.Verify("  ", followCommand(actor, target, 7), pairID); !errors.Is(err, relationshippersistence.ErrBasisRequired) {
			t.Fatal("missing basis must be its own typed failure")
		}
	})

	t.Run("another audience cannot reuse the basis", func(t *testing.T) {
		other, err := relationshippersistence.NewMutationBasisSigner(
			"user-service.beta",
			basisTestKeyID,
			[]relationshippersistence.MutationBasisKey{
				{ID: basisTestKeyID, Material: []byte(strings.Repeat("k", 32))},
			},
		)
		if err != nil {
			t.Fatal(err)
		}
		if _, err := other.WithClock(func() time.Time { return issuedAt }).
			Verify(token, followCommand(actor, target, 7), pairID); !errors.Is(err, relationshippersistence.ErrBasisInvalid) {
			t.Fatalf("cross-audience basis error = %v, want ErrBasisInvalid", err)
		}
	})
}

func TestMutationBasisExpiresWithoutRenewalOnRetry(t *testing.T) {
	t.Parallel()

	const (
		actor  = "basis-expiry-actor"
		target = "basis-expiry-target"
		pairID = "basis-expiry-pair"
	)
	issuedAt := time.Date(2026, 9, 18, 0, 0, 0, 0, time.UTC)
	current := issuedAt
	signer := newBasisSigner(t, func() time.Time { return current })
	token, err := signer.Issue(relationshipapp.MutationBasisClaims{
		ActorPersonaID:  actor,
		TargetPersonaID: target,
		PairID:          pairID,
		ExpectedVersion: 1,
		AllowedActions:  []relmodel.CommandKind{relmodel.CommandFollow},
	})
	if err != nil {
		t.Fatal(err)
	}

	// 接受窗口内可用，且多次重试不刷新期限。
	current = issuedAt.Add(71 * time.Hour)
	if _, err := signer.Verify(token, followCommand(actor, target, 1), pairID); err != nil {
		t.Fatalf("basis inside the accept window must verify, got %v", err)
	}
	current = issuedAt.Add(72 * time.Hour)
	if _, err := signer.Verify(token, followCommand(actor, target, 1), pairID); !errors.Is(err, relationshippersistence.ErrBasisExpired) {
		t.Fatalf("basis at the deadline error = %v, want ErrBasisExpired", err)
	}
	current = issuedAt.Add(100 * time.Hour)
	if _, err := signer.Verify(token, followCommand(actor, target, 1), pairID); !errors.Is(err, relationshippersistence.ErrBasisExpired) {
		t.Fatal("retrying an expired basis must not renew it")
	}
}

func TestMutationBasisSignerRefusesUnusableKeyring(t *testing.T) {
	t.Parallel()

	usable := []relationshippersistence.MutationBasisKey{
		{ID: basisTestKeyID, Material: []byte(strings.Repeat("k", 32))},
	}
	cases := map[string]func() error{
		"missing audience": func() error {
			_, err := relationshippersistence.NewMutationBasisSigner("", basisTestKeyID, usable)
			return err
		},
		"missing active key id": func() error {
			_, err := relationshippersistence.NewMutationBasisSigner(basisTestAudience, "", usable)
			return err
		},
		"active key not in keyring": func() error {
			_, err := relationshippersistence.NewMutationBasisSigner(basisTestAudience, "other", usable)
			return err
		},
		"short key material": func() error {
			_, err := relationshippersistence.NewMutationBasisSigner(
				basisTestAudience,
				basisTestKeyID,
				[]relationshippersistence.MutationBasisKey{{ID: basisTestKeyID, Material: []byte("short")}},
			)
			return err
		},
	}
	for name, build := range cases {
		if err := build(); err == nil {
			t.Fatalf("%s must fail closed at construction", name)
		}
	}
}

func blockCommandFor(source, target string) relmodel.Command {
	return relmodel.Command{
		Kind:            relmodel.CommandBlock,
		SourcePersonaID: source,
		TargetPersonaID: target,
	}
}

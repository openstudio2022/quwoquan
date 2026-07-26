package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"os"
	"strings"
	"sync"

	"quwoquan_service/services/content-service/internal/content/post/infrastructure/accountclosure"
)

const accountClosureSubjectHMACEnv = "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"

type subjectClosureLookup interface {
	IsSubjectClosed(ctx context.Context, subjectID string) (bool, error)
}

type deferredSubjectClosureGuard struct {
	mu       sync.RWMutex
	delegate subjectClosureLookup
}

func newDeferredSubjectClosureGuard() *deferredSubjectClosureGuard {
	return &deferredSubjectClosureGuard{}
}

func (guard *deferredSubjectClosureGuard) Bind(
	delegate subjectClosureLookup,
) error {
	if guard == nil || delegate == nil {
		return errors.New("subject-closure guard delegate is required")
	}
	guard.mu.Lock()
	defer guard.mu.Unlock()
	if guard.delegate != nil {
		return errors.New("subject-closure guard delegate is already bound")
	}
	guard.delegate = delegate
	return nil
}

func (guard *deferredSubjectClosureGuard) IsSubjectClosed(
	ctx context.Context,
	subjectID string,
) (bool, error) {
	if guard == nil {
		return false, errors.New("subject-closure guard is not configured")
	}
	guard.mu.RLock()
	delegate := guard.delegate
	guard.mu.RUnlock()
	if delegate == nil {
		return false, errors.New("subject-closure guard is not bound")
	}
	return delegate.IsSubjectClosed(ctx, subjectID)
}

func resolveAccountClosureSubjectDigestor(
	appEnv string,
	serviceName string,
) (accountclosure.SubjectDigestor, error) {
	secret := strings.TrimSpace(os.Getenv(accountClosureSubjectHMACEnv))
	if secret == "" {
		if appEnv != "alpha" {
			return nil, errors.New(
				accountClosureSubjectHMACEnv + " is required outside alpha",
			)
		}
		// Alpha 仅承载合成数据；派生键避免把固定 secret 写入仓库。
		sum := sha256.Sum256([]byte(serviceName + "\x00" + appEnv))
		secret = hex.EncodeToString(sum[:])
	}
	return accountclosure.NewHMACSubjectDigestor(secret)
}

package bootstrap

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"log/slog"
	"os"
	"strings"
	"sync"
	"time"

	rthealth "quwoquan_service/runtime/health"
	rtredis "quwoquan_service/runtime/redis"
	closurestream "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/adapters/inbound/stream"
	closureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
	"quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/infrastructure/accountclosure"
	recinfra "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	mediainfra "quwoquan_service/services/content-service/internal/media/media_asset/infrastructure/media"

	"go.mongodb.org/mongo-driver/v2/mongo"
)

const accountClosureSubjectHMACEnv = "CONTENT_ACCOUNT_CLOSURE_SUBJECT_HMAC_SECRET"

type subjectClosureLookup interface {
	IsSubjectClosed(ctx context.Context, subjectID string) (bool, error)
}

type contentAccountRestrictionProjection interface {
	accountclosure.AccountRestrictionProjection
	recinfra.AccountRestrictionReader
	EnsureIndexes(ctx context.Context) error
}

func newContentAccountRestrictionProjection(
	db *mongo.Database,
	closedSubjects accountclosure.PersistentSubjectClosureLookup,
) (contentAccountRestrictionProjection, error) {
	return accountclosure.NewAccountRestrictionProjection(db, closedSubjects)
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

func startAccountClosureRuntime(
	ctx context.Context,
	workers *workerRegistry,
	redis rtredis.Client,
	logger *slog.Logger,
	healthChecker *rthealth.Checker,
	instanceID string,
	store *accountclosure.MongoStore,
	cache *accountclosure.RedisPersonalDataCacheCleaner,
	search *accountclosure.SearchIndexerDeleter,
	media *mediainfra.ObjectGateway,
	restrictions accountclosure.AccountRestrictionProjection,
) (*accountclosure.Consumer, error) {
	if restrictions == nil {
		return nil, errors.New(
			"content account restriction projection is required",
		)
	}
	processor, err := accountclosure.NewProcessor(store, cache, search, media)
	if err != nil {
		return nil, err
	}
	consumer, err := accountclosure.NewConsumer(
		redis,
		closurestream.NewHandler(closureapp.NewIngress(processor)),
		store,
		"content-service-"+instanceID,
		logger,
		accountclosure.DefaultConsumerConfig(),
	)
	if err != nil {
		return nil, err
	}
	consumer.WithAccountRestrictionProjection(restrictions)
	if err := consumer.EnsureGroup(ctx); err != nil {
		return nil, err
	}
	workers.Add(consumer.Run)
	healthChecker.Register("user-account-closed-consumer", func(context.Context) error {
		return consumer.Healthy(15 * time.Second)
	})
	return consumer, nil
}

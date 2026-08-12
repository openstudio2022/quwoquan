// Package ports 定义 AuthenticationChallenge 对象专属 Store 与凭据验证端口。
package ports

import (
	"context"
	"errors"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
)

var ErrIdempotencyConflict = errors.New(
	"authentication challenge idempotency conflict",
)

// CreateCommit 将新聚合与创建幂等回执作为一个提交单元。CommandFingerprint
// 只能由非明文业务维度派生，禁止包含原始凭据。
type CreateCommit struct {
	Aggregate          challengemodel.AuthenticationChallenge
	IdempotencyKey     string
	CommandFingerprint string
}

type CreateResult struct {
	Aggregate challengemodel.AuthenticationChallenge
	Replayed  bool
}

type LatestChallengeLookup struct {
	Purpose         string
	Channel         string
	DestinationHash string
}

// AggregateStore 是 AuthenticationChallenge 唯一权威数据端口。
// Create 必须把状态与创建回执原子提交；Commit 必须用 expectedVersion 做
// 服务端内部 CAS，并在同一行原子写入状态与 completion fingerprint。
// metadata events.yaml 当前为空，因此本对象不制造纸面 outbox。
type AggregateStore interface {
	Create(ctx context.Context, commit CreateCommit) (CreateResult, error)
	LoadByID(
		ctx context.Context,
		challengeID string,
	) (challengemodel.AuthenticationChallenge, bool, error)
	LoadLatest(
		ctx context.Context,
		lookup LatestChallengeLookup,
	) (challengemodel.AuthenticationChallenge, bool, error)
	LoadByDeliveryRequestID(
		ctx context.Context,
		requestID string,
	) (challengemodel.AuthenticationChallenge, bool, error)
	Commit(
		ctx context.Context,
		expectedVersion int64,
		aggregate challengemodel.AuthenticationChallenge,
	) error
}

// CredentialVerificationInput 只在一次 application 调用期间存活。
// Credential 为明文瞬时输入，任何实现都不得记录、持久化或进入事件。
type CredentialVerificationInput struct {
	ChallengeID     string
	Purpose         string
	Channel         string
	DestinationHash string
	SecretRef       string
	Credential      []byte
}

type CredentialVerificationEvidence struct {
	CompletionFingerprint string
	Matched               bool
}

// CredentialVerifier 通过不可逆 secretRef 校验瞬时凭据，并返回稳定凭据指纹。
// 相同凭据必须得到相同 CompletionFingerprint，供 completed 行内回执重放。
type CredentialVerifier interface {
	VerifyCredential(
		ctx context.Context,
		input CredentialVerificationInput,
	) (CredentialVerificationEvidence, error)
}

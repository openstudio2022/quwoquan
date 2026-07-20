package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
)

const chatCommandReceiptTTL = 24 * time.Hour

// scopedChatIdempotencyKey 把 transport 层 Idempotency-Key 与 actor 绑定，
// 不同 actor 复用同一外部 key 互不影响。
func scopedChatIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	current, _ := operation.FromContext(ctx)
	rawKey := strings.TrimSpace(current.IdempotencyKey)
	if rawKey == "" {
		return "", rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"命令缺少幂等标识",
			"chat command requires Idempotency-Key",
		)
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "chat:" + hex.EncodeToString(sum[:]), nil
}

// chatCommandDigest 序列化命令语义负载，用于拒绝同 key 不同命令的重放。
func chatCommandDigest(commandName string, payload any) (string, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return "", fmt.Errorf("encode %s command digest: %w", commandName, err)
	}
	sum := sha256.Sum256(append([]byte(commandName+"\x00"), encoded...))
	return hex.EncodeToString(sum[:]), nil
}

// chatAggregateEventID 由幂等回执键与事件类型派生稳定事件 ID，重试不会
// 产生第二个事件文档。
func chatAggregateEventID(scopedKey, eventType string) string {
	sum := sha256.Sum256([]byte(scopedKey + "\x00" + eventType))
	return "chatevt_" + hex.EncodeToString(sum[:16])
}

// replayChatCommand 在命令入口做幂等重放短路。found 时把首个结果反序列
// 化进 result（可为 nil 表示无返回体命令）。
func replayChatCommand(
	ctx context.Context,
	store AggregateCommandStore,
	scopedKey string,
	commandName string,
	commandDigest string,
	result any,
) (bool, error) {
	raw, found, err := store.FindAggregateCommandReceipt(ctx, scopedKey, commandName, commandDigest)
	if err != nil {
		return false, mapChatIdempotencyError(err)
	}
	if !found {
		return false, nil
	}
	if result != nil && len(raw) > 0 {
		if err := json.Unmarshal(raw, result); err != nil {
			return false, fmt.Errorf("decode replayed %s result: %w", commandName, err)
		}
	}
	return true, nil
}

func chatCommandReceipt(
	scopedKey string,
	commandName string,
	commandDigest string,
	aggregateID string,
	result any,
) (AggregateCommandReceipt, error) {
	receipt := AggregateCommandReceipt{
		IdempotencyKey: scopedKey,
		CommandName:    commandName,
		CommandDigest:  commandDigest,
		AggregateID:    aggregateID,
		ExpiresAt:      time.Now().UTC().Add(chatCommandReceiptTTL),
	}
	if result != nil {
		encoded, err := json.Marshal(result)
		if err != nil {
			return AggregateCommandReceipt{}, fmt.Errorf("encode %s receipt result: %w", commandName, err)
		}
		receipt.ResultJSON = encoded
	}
	return receipt, nil
}

// mapChatIdempotencyError 把存储层的幂等冲突映射为结构化用户错误。
func mapChatIdempotencyError(err error) error {
	if err == nil {
		return nil
	}
	if strings.Contains(err.Error(), "idempotency key was reused") {
		return rterr.NewAppError(
			rterr.NewCode(rterr.ModuleChat, rterr.KindUser, "message_idempotency_conflict"),
			"该请求标识已用于不同内容，请重新发起",
			"idempotency key was reused with a different chat command",
		)
	}
	return err
}

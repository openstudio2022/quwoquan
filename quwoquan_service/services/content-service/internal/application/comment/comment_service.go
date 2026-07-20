package comment

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"slices"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/services/content-service/internal/application/commandmeta"
	commentmodel "quwoquan_service/services/content-service/internal/domain/comment/model"
	commentports "quwoquan_service/services/content-service/internal/domain/comment/ports"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

const (
	commentReceiptTTL = 24 * time.Hour

	commentCreatedEventType          = "CommentCreated"
	commentDeletedEventType          = "CommentDeleted"
	commentModeratedEventType        = "CommentModerated"
	commentPinChangedEventType       = "CommentPinChanged"
	commentAttachmentsBoundEventType = "CommentAttachmentsBound"
)

// RateLimitConfig 是 CreateComment 频控滑动窗口配置；阈值 <=0 表示对应窗口关闭。
type RateLimitConfig struct {
	BurstWindow time.Duration
	BurstMax    int64
	DailyWindow time.Duration
	DailyMax    int64
}

// DefaultRateLimitConfig 与 config.yaml 默认口径一致：30s ≤ 5 条且 24h ≤ 200 条。
func DefaultRateLimitConfig() RateLimitConfig {
	return RateLimitConfig{
		BurstWindow: 30 * time.Second,
		BurstMax:    5,
		DailyWindow: 24 * time.Hour,
		DailyMax:    200,
	}
}

// IPLocationResolver 把创建评论的客户端 IP 解析为省级属地快照；
// 解析不出返回空串（前端不展示，绝不臆造）。
type IPLocationResolver interface {
	Resolve(ip string) string
}

// CommentService is the object-specific application service. All dependencies
// are Comment domain ports; it neither imports infrastructure nor PostService.
type CommentService struct {
	data       DataPorts
	now        func() time.Time
	rateLimit  RateLimitConfig
	ipResolver IPLocationResolver
	clientIP   func(context.Context) string
}

type CommentServiceOption func(*CommentService)

// WithRateLimitConfig 覆盖默认频控窗口（config.yaml 驱动）。
func WithRateLimitConfig(config RateLimitConfig) CommentServiceOption {
	return func(s *CommentService) { s.rateLimit = config }
}

// WithIPLocationResolver 注入属地解析器（生产注入真实 GeoIP 实现）。
func WithIPLocationResolver(resolver IPLocationResolver) CommentServiceOption {
	return func(s *CommentService) {
		if resolver != nil {
			s.ipResolver = resolver
		}
	}
}

// WithClientIPExtractor 注入请求级客户端 IP 读取函数（HTTP 适配层注入 context）。
func WithClientIPExtractor(extract func(context.Context) string) CommentServiceOption {
	return func(s *CommentService) {
		if extract != nil {
			s.clientIP = extract
		}
	}
}

func NewCommentService(data DataPorts, opts ...CommentServiceOption) *CommentService {
	if data.Aggregate == nil ||
		data.PostPage == nil ||
		data.ReplyPage == nil ||
		data.ReplySummary == nil ||
		data.AuthorPage == nil ||
		data.ReceivedPage == nil ||
		data.Counts == nil ||
		data.Relations == nil ||
		data.PostRelation == nil ||
		data.Attachments == nil ||
		data.Reactions == nil ||
		data.ViewerRelations == nil ||
		data.ViewerBlocks == nil {
		panic("CommentService requires all object-specific data ports")
	}
	s := &CommentService{
		data:      data,
		now:       time.Now,
		rateLimit: DefaultRateLimitConfig(),
		clientIP:  func(context.Context) string { return "" },
	}
	for _, opt := range opts {
		opt(s)
	}
	return s
}

func (s *CommentService) CreateComment(
	ctx context.Context,
	command CreateCommentCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := createCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "CreateComment", commandDigest); err != nil || found {
		return replayed, err
	}
	postID := strings.TrimSpace(command.PostID)
	post, found, err := s.data.PostRelation.FindPostOwnership(ctx, postID)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if !found || !post.Active {
		return CommentCommandResult{}, contentgenerated.AppErrorFromPostNotFound(
			fmt.Sprintf("post %s is unavailable for comment creation", postID),
		)
	}

	params := commentmodel.CreateParams{
		PostID:                    postID,
		AuthorID:                  actorID,
		AuthorDisplayNameSnapshot: command.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   command.AuthorAvatarURLSnapshot,
		PersonaContextVersion:     command.PersonaContextVersion,
		Content:                   command.Content,
		AttachmentMediaIDs:        cloneStrings(command.AttachmentMediaIDs),
		Mentions:                  cloneMentions(command.Mentions),
		AssistantMentioned:        containsAssistantMention(command.Mentions),
		AuthorIPLocation:          s.resolveAuthorIPLocation(ctx),
		Now:                       s.now().UTC(),
	}
	if replyID := strings.TrimSpace(command.ReplyToCommentID); replyID != "" {
		target, targetFound, relationErr := s.data.Relations.FindReplyTarget(ctx, replyID)
		if relationErr != nil {
			return CommentCommandResult{}, unavailable(relationErr)
		}
		if !targetFound ||
			target.Status != commentmodel.StatusActive ||
			strings.TrimSpace(target.PostID) != postID {
			return CommentCommandResult{}, invalidArgument("reply target is absent, deleted, or belongs to another post")
		}
		params.ReplyToCommentID = target.ID
		params.ReplyToUserID = target.AuthorID
		params.ParentCommentID = target.ParentCommentID
		if params.ParentCommentID == "" {
			params.ParentCommentID = target.ID
		}
	}
	if err := s.data.Attachments.ValidateCommentAttachments(ctx, actorID, params.AttachmentMediaIDs); err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}

	commentID, err := newIdentifier("cmt")
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	params.ID = commentID
	aggregate, err := commentmodel.Create(params)
	if err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}
	payload, err := json.Marshal(commentCreatedEvent{
		CommentID:        aggregate.ID(),
		Version:          aggregate.Version(),
		PostID:           params.PostID,
		PostAuthorID:     post.AuthorID,
		AuthorID:         actorID,
		ReplyToCommentID: params.ReplyToCommentID,
		ReplyToUserID:    params.ReplyToUserID,
		ParentCommentID:  params.ParentCommentID,
		MentionedUserIDs: mentionedUserIDs(params.Mentions),
		CreatedAt:        params.Now.UTC(),
	})
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	return s.commitWithAuthorRateLimit(
		ctx,
		actorID,
		aggregate,
		0,
		"CreateComment",
		commandDigest,
		commentCreatedEventType,
		payload,
		params.Now,
		s.authorRateLimit(actorID, params.Now),
	)
}

func (s *CommentService) DeleteComment(
	ctx context.Context,
	command DeleteCommentCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := deleteCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "DeleteComment", commandDigest); err != nil || found {
		return replayed, err
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found || aggregate.Snapshot().PostID != strings.TrimSpace(command.PostID) {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if aggregate.Status() == commentmodel.StatusDeleted {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				"DeleteComment",
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if deleteErr := aggregate.Delete(actorID, now); deleteErr != nil {
			return CommentCommandResult{}, mapDomainError(deleteErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentDeletedEvent{
			CommentID:       snapshot.ID,
			Version:         snapshot.Version,
			PostID:          snapshot.PostID,
			AuthorID:        snapshot.AuthorID,
			ParentCommentID: snapshot.ParentCommentID,
			DeletedAt:       now,
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"DeleteComment",
			commandDigest,
			commentDeletedEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying delete intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment delete retry")
}

func (s *CommentService) PinComment(
	ctx context.Context,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	command.Pinned = true
	return s.changePin(ctx, "PinComment", command)
}

func (s *CommentService) UnpinComment(
	ctx context.Context,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	command.Pinned = false
	return s.changePin(ctx, "UnpinComment", command)
}

func (s *CommentService) changePin(
	ctx context.Context,
	commandName string,
	command ChangeCommentPinCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := pinCommandDigest(commandName, command)
	if replayed, found, err := s.replay(ctx, actorID, commandName, commandDigest); err != nil || found {
		return replayed, err
	}
	ownership, ownershipFound, err := s.data.PostRelation.FindPostOwnership(
		ctx,
		strings.TrimSpace(command.PostID),
	)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if !ownershipFound || !ownership.Active {
		return CommentCommandResult{}, contentgenerated.AppErrorFromPostNotFound(
			fmt.Sprintf("post %s is unavailable for comment pin", command.PostID),
		)
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found || aggregate.Snapshot().PostID != strings.TrimSpace(command.PostID) {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if aggregate.Snapshot().IsPinned == command.Pinned {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				commandName,
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if pinErr := aggregate.ChangePin(actorID, ownership.AuthorID, command.Pinned, now); pinErr != nil {
			return CommentCommandResult{}, mapDomainError(pinErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentPinChangedEvent{
			CommentID:       snapshot.ID,
			Version:         snapshot.Version,
			PostID:          snapshot.PostID,
			CommentAuthorID: snapshot.AuthorID,
			OperatorID:      actorID,
			IsPinned:        snapshot.IsPinned,
			PinnedAt:        snapshot.PinnedAt,
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			commandName,
			commandDigest,
			commentPinChangedEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying pin intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment pin retry")
}

func (s *CommentService) BindAttachments(
	ctx context.Context,
	command BindCommentAttachmentsCommand,
) (CommentCommandResult, error) {
	actorID, err := requiredActorID(command.ActorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	command.ActorID = actorID
	commandDigest := bindAttachmentsCommandDigest(command)
	if replayed, found, err := s.replay(ctx, actorID, "BindCommentAttachments", commandDigest); err != nil || found {
		return replayed, err
	}
	if err := s.data.Attachments.ValidateCommentAttachments(ctx, actorID, command.AttachmentMediaIDs); err != nil {
		return CommentCommandResult{}, mapDomainError(err)
	}
	for attempt := 0; attempt < 3; attempt++ {
		aggregate, found, loadErr := s.load(ctx, command.CommentID)
		if loadErr != nil {
			return CommentCommandResult{}, loadErr
		}
		if !found {
			return CommentCommandResult{}, commentNotFound(command.CommentID)
		}
		if slices.Equal(
			aggregate.Snapshot().AttachmentMediaIDs,
			command.AttachmentMediaIDs,
		) {
			return s.recordIdempotentReceipt(
				ctx,
				actorID,
				aggregate,
				"BindCommentAttachments",
				commandDigest,
			)
		}
		expectedVersion := aggregate.Version()
		now := s.now().UTC()
		if bindErr := aggregate.BindAttachments(actorID, command.AttachmentMediaIDs, now); bindErr != nil {
			return CommentCommandResult{}, mapDomainError(bindErr)
		}
		snapshot := aggregate.Snapshot()
		payload, marshalErr := json.Marshal(commentAttachmentsBoundEvent{
			CommentID:          snapshot.ID,
			Version:            snapshot.Version,
			PostID:             snapshot.PostID,
			AuthorID:           snapshot.AuthorID,
			AttachmentMediaIDs: cloneStrings(snapshot.AttachmentMediaIDs),
		})
		if marshalErr != nil {
			return CommentCommandResult{}, unavailable(marshalErr)
		}
		result, commitErr := s.commit(
			ctx,
			actorID,
			aggregate,
			expectedVersion,
			"BindCommentAttachments",
			commandDigest,
			commentAttachmentsBoundEventType,
			payload,
			now,
		)
		if commitErr == nil {
			return result, nil
		}
		if !isCommentVersionConflict(commitErr) || attempt == 2 {
			if isCommentVersionConflict(commitErr) {
				return CommentCommandResult{}, contentgenerated.AppErrorFromVersionConflict(
					"comment changed repeatedly while applying attachment intent",
				)
			}
			return CommentCommandResult{}, commitErr
		}
	}
	panic("unreachable Comment attachment retry")
}

func (s *CommentService) load(
	ctx context.Context,
	commentID string,
) (*commentmodel.Comment, bool, error) {
	aggregate, found, err := s.data.Aggregate.Load(ctx, strings.TrimSpace(commentID))
	if err != nil {
		return nil, false, unavailable(err)
	}
	return aggregate, found, nil
}

func (s *CommentService) replay(
	ctx context.Context,
	actorID string,
	commandName string,
	commandDigest string,
) (CommentCommandResult, bool, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, false, err
	}
	result, found, err := s.data.Aggregate.FindReceipt(
		ctx,
		idempotencyKey,
		commandName,
		commandDigest,
	)
	if err != nil {
		return CommentCommandResult{}, false, unavailable(err)
	}
	if !found {
		return CommentCommandResult{}, false, nil
	}
	if result.Aggregate == nil {
		return CommentCommandResult{}, false, unavailable(errors.New("comment receipt has no aggregate"))
	}
	return commandResult(result.Aggregate, true), true, nil
}

func (s *CommentService) commit(
	ctx context.Context,
	actorID string,
	aggregate *commentmodel.Comment,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload []byte,
	now time.Time,
) (CommentCommandResult, error) {
	return s.commitWithAuthorRateLimit(
		ctx,
		actorID,
		aggregate,
		expectedVersion,
		commandName,
		commandDigest,
		eventType,
		eventPayload,
		now,
		nil,
	)
}

func (s *CommentService) commitWithAuthorRateLimit(
	ctx context.Context,
	actorID string,
	aggregate *commentmodel.Comment,
	expectedVersion int64,
	commandName string,
	commandDigest string,
	eventType string,
	eventPayload []byte,
	now time.Time,
	authorRateLimit *commentports.AuthorRateLimit,
) (CommentCommandResult, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	eventID := eventIdentifier(idempotencyKey, eventType)
	result, err := s.data.Aggregate.Commit(ctx, commentports.Commit{
		Aggregate:        aggregate,
		ExpectedVersion:  expectedVersion,
		IdempotencyKey:   idempotencyKey,
		CommandName:      commandName,
		CommandDigest:    commandDigest,
		ReceiptExpiresAt: now.UTC().Add(commentReceiptTTL),
		AuthorRateLimit:  authorRateLimit,
		Events: []commentports.OutboxEvent{{
			EventID:          eventID,
			EventType:        eventType,
			AggregateID:      aggregate.ID(),
			AggregateVersion: aggregate.Version(),
			Payload:          append([]byte(nil), eventPayload...),
			OccurredAt:       now.UTC(),
		}},
	})
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return CommentCommandResult{}, unavailable(errors.New("comment commit returned no aggregate"))
	}
	return commandResult(result.Aggregate, result.Replayed), nil
}

func (s *CommentService) recordIdempotentReceipt(
	ctx context.Context,
	actorID string,
	aggregate *commentmodel.Comment,
	commandName string,
	commandDigest string,
) (CommentCommandResult, error) {
	idempotencyKey, err := scopedIdempotencyKey(ctx, actorID)
	if err != nil {
		return CommentCommandResult{}, err
	}
	result, err := s.data.Aggregate.RecordIdempotentReceipt(
		ctx,
		commentports.IdempotentReceipt{
			Aggregate:        aggregate,
			IdempotencyKey:   idempotencyKey,
			CommandName:      commandName,
			CommandDigest:    commandDigest,
			ReceiptExpiresAt: s.now().UTC().Add(commentReceiptTTL),
		},
	)
	if err != nil {
		return CommentCommandResult{}, unavailable(err)
	}
	if result.Aggregate == nil {
		return CommentCommandResult{},
			unavailable(errors.New("comment no-op receipt returned no aggregate"))
	}
	return commandResult(result.Aggregate, result.Replayed), nil
}

func commandResult(aggregate *commentmodel.Comment, replayed bool) CommentCommandResult {
	return CommentCommandResult{
		ID:       aggregate.ID(),
		Version:  aggregate.Version(),
		Status:   aggregate.Status(),
		Replayed: replayed,
	}
}

func requiredActorID(raw string) (string, error) {
	actorID := strings.TrimSpace(raw)
	if actorID == "" {
		return "", contentgenerated.AppErrorFromUnauthorized(
			"comment command or private reader requires an authenticated persona actor",
		)
	}
	return actorID, nil
}

func scopedIdempotencyKey(ctx context.Context, actorID string) (string, error) {
	rawKey := strings.TrimSpace(commandmeta.IdempotencyKey(ctx))
	if rawKey == "" {
		return "", invalidArgument("comment command requires Idempotency-Key")
	}
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + rawKey))
	return "comment:" + hex.EncodeToString(sum[:]), nil
}

func mapDomainError(err error) error {
	switch {
	case errors.Is(err, commentmodel.ErrDeleteForbidden):
		return contentgenerated.AppErrorFromCommentForbiddenDelete(err.Error())
	case errors.Is(err, commentmodel.ErrPinForbidden):
		return contentgenerated.AppErrorFromCommentPinForbidden(err.Error())
	case errors.Is(err, commentmodel.ErrPinInvalidTarget):
		return contentgenerated.AppErrorFromCommentPinInvalidTarget(err.Error())
	case errors.Is(err, commentmodel.ErrCommentDeleted):
		return contentgenerated.AppErrorFromCommentNotFound(err.Error())
	case errors.Is(err, commentmodel.ErrAttachmentForbidden):
		return contentgenerated.AppErrorFromCommentForbiddenDelete(err.Error())
	case errors.Is(err, commentmodel.ErrModerationForbidden):
		return contentgenerated.AppErrorFromCommentModerationForbidden(err.Error())
	case errors.Is(err, commentmodel.ErrInvalidStatusTransition):
		return contentgenerated.AppErrorFromCommentStatusTransitionInvalid(err.Error())
	case errors.Is(err, commentmodel.ErrInvalidReplyTarget),
		errors.Is(err, commentmodel.ErrInvalidComment),
		errors.Is(err, commentmodel.ErrInvalidMutationClock):
		return invalidArgument(err.Error())
	default:
		return err
	}
}

func isCommentVersionConflict(err error) bool {
	var appError *rterr.AppError
	return errors.As(err, &appError) &&
		appError.Code.String() == contentgenerated.ErrVersionConflict.Error()
}

func commentNotFound(commentID string) error {
	return contentgenerated.AppErrorFromCommentNotFound(
		fmt.Sprintf("comment %s not found", strings.TrimSpace(commentID)),
	)
}

func invalidArgument(debug string) error {
	return contentgenerated.AppErrorFromInvalidArgument(debug)
}

func unavailable(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageWriteFailed(err.Error())
}

func unavailableRead(err error) error {
	var appError *rterr.AppError
	if errors.As(err, &appError) {
		return appError
	}
	return contentgenerated.AppErrorFromStorageReadFailed(err.Error())
}

func createCommandDigest(command CreateCommentCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("CreateComment", raw)
}

func deleteCommandDigest(command DeleteCommentCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("DeleteComment", raw)
}

func pinCommandDigest(commandName string, command ChangeCommentPinCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload(commandName, raw)
}

func bindAttachmentsCommandDigest(command BindCommentAttachmentsCommand) string {
	raw, _ := json.Marshal(command)
	return digestPayload("BindCommentAttachments", raw)
}

func digestPayload(commandName string, payload []byte) string {
	h := sha256.New()
	_, _ = h.Write([]byte(commandName))
	_, _ = h.Write([]byte{0})
	_, _ = h.Write(payload)
	sum := h.Sum(nil)
	return hex.EncodeToString(sum[:])
}

func eventIdentifier(idempotencyKey, eventType string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(idempotencyKey) + ":" + eventType))
	return "evt_" + hex.EncodeToString(sum[:16])
}

func newIdentifier(prefix string) (string, error) {
	var raw [16]byte
	if _, err := rand.Read(raw[:]); err != nil {
		return "", err
	}
	return prefix + "_" + hex.EncodeToString(raw[:]), nil
}

func cloneStrings(values []string) []string {
	if len(values) == 0 {
		return []string{}
	}
	cloned := make([]string, 0, len(values))
	for _, value := range values {
		if value = strings.TrimSpace(value); value != "" {
			cloned = append(cloned, value)
		}
	}
	return cloned
}

func cloneMentions(values []commentmodel.Mention) []commentmodel.Mention {
	if len(values) == 0 {
		return []commentmodel.Mention{}
	}
	cloned := make([]commentmodel.Mention, len(values))
	copy(cloned, values)
	return cloned
}

func containsAssistantMention(mentions []commentmodel.Mention) bool {
	for _, mention := range mentions {
		if strings.EqualFold(strings.TrimSpace(mention.SubjectType), "assistant") {
			return true
		}
	}
	return false
}

// mentionedUserIDs 从 typed mentions 中提取用户主体 id，供 @提及通知消费；
// 助手等非用户主体不进入该列表。
func mentionedUserIDs(mentions []commentmodel.Mention) []string {
	ids := make([]string, 0, len(mentions))
	seen := map[string]struct{}{}
	for _, mention := range mentions {
		if !strings.EqualFold(strings.TrimSpace(mention.SubjectType), "user") {
			continue
		}
		id := strings.TrimSpace(mention.SubjectID)
		if id == "" {
			continue
		}
		if _, dup := seen[id]; dup {
			continue
		}
		seen[id] = struct{}{}
		ids = append(ids, id)
	}
	return ids
}

// authorRateLimit 把 burst + daily 滑动窗口编译为 Store 事务约束。
// 校验与 Comment/receipt/outbox 同事务提交，避免多实例并发先读后写超卖。
func (s *CommentService) authorRateLimit(
	actorID string,
	now time.Time,
) *commentports.AuthorRateLimit {
	windows := make([]commentports.AuthorRateWindow, 0, 2)
	for _, configured := range []struct {
		window time.Duration
		max    int64
	}{
		{s.rateLimit.BurstWindow, s.rateLimit.BurstMax},
		{s.rateLimit.DailyWindow, s.rateLimit.DailyMax},
	} {
		if configured.window <= 0 || configured.max <= 0 {
			continue
		}
		windows = append(windows, commentports.AuthorRateWindow{
			Since: now.UTC().Add(-configured.window),
			Max:   configured.max,
		})
	}
	if len(windows) == 0 {
		return nil
	}
	return &commentports.AuthorRateLimit{
		AuthorID:    strings.TrimSpace(actorID),
		EvaluatedAt: now.UTC(),
		Windows:     windows,
	}
}

// resolveAuthorIPLocation 在创建时解析属地快照；未注入 resolver 或解析失败落空串。
func (s *CommentService) resolveAuthorIPLocation(ctx context.Context) string {
	if s.ipResolver == nil {
		return ""
	}
	ip := strings.TrimSpace(s.clientIP(ctx))
	if ip == "" {
		return ""
	}
	return strings.TrimSpace(s.ipResolver.Resolve(ip))
}

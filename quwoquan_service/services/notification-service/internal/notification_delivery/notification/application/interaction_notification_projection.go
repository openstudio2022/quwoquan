package application

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"time"

	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

// 互动通知投影规则唯一真相源：
// specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md
// 七源触发矩阵。幂等键由 event identity + 投递 identity 生成；自互动、取关、
// reaction 清除、未开启陌生人招呼等条件返回 nil 跳过，不产生通知。

// InteractionStreamEvent 是 durable Redis Stream 消息的归一化视图。
// content 系事件携带 JSON payload；user/circle 系事件为扁平字段。
type InteractionStreamEvent struct {
	Stream     string
	MessageID  string
	EventID    string
	EventType  string
	Values     map[string]string
	Payload    []byte
	OccurredAt time.Time
}

// InteractionNotificationStreams 是通知消费者订阅的 durable stream 清单，
// 与各生产者 publisher 的 stream key 常量对齐（消费侧不自造第二真相源，
// 但为避免跨服务 internal import，在此按契约固定并由 api_integration 校验）。
var InteractionNotificationStreams = []string{
	"events.content.comment_lifecycle",
	"events.content.reaction_lifecycle",
	"events.content.post_lifecycle",
	"events.content.report_lifecycle",
	"events.user.persona_relationship",
	"events.user.greeting",
	"events.circle.memberships",
	"events.circle.group-memberships",
	"events.circle.gatherings",
	"events.entity.homepage_lifecycle",
	"events.recommendation.intersections",
}

const (
	interactionTitleComment        = "新的评论"
	interactionTitleReply          = "新的回复"
	interactionTitleMention        = "有人@了你"
	interactionTitlePinned         = "评论被置顶"
	interactionTitleLike           = "收到点赞"
	interactionTitleQuote          = "作品被引用"
	interactionTitleFollow         = "新的关注者"
	interactionTitleGreeting       = "收到打招呼"
	interactionTitleCircleJoin     = "圈子新成员"
	interactionTitleCircleRequest  = "圈子加入申请"
	interactionTitleCircleResult   = "圈子申请结果"
	interactionTitleGroupRequest   = "群组加入申请"
	interactionTitleGroupResult    = "群组申请结果"
	interactionTitleReportResult   = "举报处理完成"
	interactionTitleClaimResult    = "主页认领审核完成"
	interactionTitleStatusResult   = "主页状态上报处理完成"
	interactionTitleFacilitation   = "你的内容促成了一次成行"
	interactionTitleInviteAccepted = "邀约有了回音"
	interactionTitleInviteDeclined = "邀约已回复"
)

// InteractionNotificationProjection 是 durable interaction stream 的唯一应用入口。
// 它既生成属于触发矩阵的 AppMessage command，也明确确认无需通知的同流事件。
type InteractionNotificationProjection struct{}

// Project 将一条 durable 互动事件映射为零或多条
// CreateAppMessageCommand（如 CommentCreated 同时产生回复通知与 @提及通知）。
// 返回空切片表示按触发矩阵跳过；返回 error 表示事件不完整
// （进入失败计数与 DLQ），绝不伪造接收者。
func (InteractionNotificationProjection) Project(
	event InteractionStreamEvent,
) ([]*CreateAppMessageCommand, error) {
	switch event.EventType {
	case "CommentCreated":
		return projectCommentCreated(event)
	case "CommentPinChanged":
		return single(projectCommentPinChanged(event))
	case "ContentReactionSet":
		return single(projectReactionSet(event))
	case "PostPublished":
		return single(projectQuotedPublish(event))
	case "content.report.ReportResolved", "content.report.ReportDismissed":
		return single(projectReportResult(event))
	case "PersonaFollowStateChanged":
		return single(projectFollowChanged(event))
	case "GreetingRequestSent":
		return single(projectGreetingSent(event))
	case "CircleMembershipJoined":
		return single(projectCircleJoined(event))
	case "CircleMembershipRequested", "CircleMembershipApproved", "CircleMembershipRejected":
		return single(projectCircleMembershipDecision(event))
	case "CircleGroupMembershipRequested",
		"CircleGroupMembershipActivated",
		"CircleGroupMembershipRejected":
		return single(projectGroupMembership(event))
	case "HomepageClaimReviewed":
		return single(projectHomepageClaimResult(event))
	case "HomepageStatusReportReviewed":
		return single(projectHomepageStatusResult(event))
	case "IntersectionFacilitationRecorded":
		return single(projectIntersectionFacilitation(event))
	case "GatheringInvitationChanged":
		return single(projectInvitationInviterReceipt(event))
	default:
		// 同一 stream 上的其它生命周期事件（删除、退出、清除等）
		// 不属于触发矩阵，直接确认跳过。
		return nil, nil
	}
}

// projectInvitationInviterReceipt 是邀请回执的发起方侧分支：受邀方对邀约
// 作出真实应答（accepted/declined）时给邀请方一条回执通知，让 1对1 邀约
// 不再石沉大海。受邀方自己的邀请卡由 GatheringInvitationProjection 独立
// upsert，两者互不干扰。pending（无应答事实）、revoked（邀请方自己操作）、
// expired/cancelled（系统终态）不生成回执；declined 文案克制，不羞辱不催促。
func projectInvitationInviterReceipt(
	event InteractionStreamEvent,
) (*CreateAppMessageCommand, error) {
	var payload struct {
		GatheringID        string `json:"gatheringId"`
		InviterPersonaID   string `json:"inviterPersonaId"`
		RecipientPersonaID string `json:"recipientPersonaId"`
		Status             string `json:"status"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode gathering invitation receipt payload: %w", err)
	}
	status := strings.TrimSpace(payload.Status)
	if status != "accepted" && status != "declined" {
		return nil, nil
	}
	if strings.TrimSpace(payload.GatheringID) == "" ||
		strings.TrimSpace(payload.InviterPersonaID) == "" ||
		strings.TrimSpace(payload.RecipientPersonaID) == "" {
		return nil, fmt.Errorf("gathering invitation receipt identity is incomplete")
	}
	title := interactionTitleInviteAccepted
	summary := "对方接受了你的邀约，打开看看这次行动"
	if status == "declined" {
		title = interactionTitleInviteDeclined
		summary = "对方这次不方便，名额已释放，可以再邀请其他同好"
	}
	return interactionCommand(
		event,
		payload.InviterPersonaID,
		"circle",
		"gathering_invitation_receipt",
		payload.GatheringID+":"+status,
		title,
		summary,
		notification.AppMessageTarget{
			TargetType: "gathering",
			TargetID:   payload.GatheringID,
		},
	), nil
}

// projectIntersectionFacilitation 把 recommendation 的创作者促成事实映射为
// 一条内容维度通知：只携带公开经历引用（回链 Gathering 公开详情），
// 不暴露参与者名单；同一 (gathering, creator, seedPost) 由事件 identity 幂等。
func projectIntersectionFacilitation(
	event InteractionStreamEvent,
) (*CreateAppMessageCommand, error) {
	var payload struct {
		FacilitationID   string `json:"facilitationId"`
		GatheringID      string `json:"gatheringId"`
		CreatorPersonaID string `json:"creatorPersonaId"`
		SeedPostID       string `json:"seedPostId"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode intersection facilitation payload: %w", err)
	}
	if strings.TrimSpace(payload.FacilitationID) == "" ||
		strings.TrimSpace(payload.GatheringID) == "" ||
		strings.TrimSpace(payload.CreatorPersonaID) == "" ||
		strings.TrimSpace(payload.SeedPostID) == "" {
		return nil, fmt.Errorf("intersection facilitation identity is incomplete")
	}
	return interactionCommand(
		event,
		payload.CreatorPersonaID,
		"content",
		"intersection_facilitation",
		payload.FacilitationID,
		interactionTitleFacilitation,
		"有人从你的内容出发一起去了，点开看这次共同经历",
		notification.AppMessageTarget{
			TargetType: "gathering",
			TargetID:   payload.GatheringID,
		},
	), nil
}

func projectHomepageClaimResult(
	event InteractionStreamEvent,
) (*CreateAppMessageCommand, error) {
	var payload struct {
		ClaimRequestID     string `json:"claimRequestId"`
		HomepageID         string `json:"homepageId"`
		RequesterPersonaID string `json:"requesterPersonaId"`
		Status             string `json:"status"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode homepage claim result payload: %w", err)
	}
	if strings.TrimSpace(payload.ClaimRequestID) == "" ||
		strings.TrimSpace(payload.HomepageID) == "" ||
		strings.TrimSpace(payload.RequesterPersonaID) == "" {
		return nil, fmt.Errorf("homepage claim result identity is incomplete")
	}
	summary := "你的主页认领申请已通过，可以开始维护主页信息"
	if payload.Status == "rejected" {
		summary = "你的主页认领申请未通过，请查看审核结果后重新提交"
	}
	return interactionCommand(
		event,
		payload.RequesterPersonaID,
		"entity",
		"homepage_claim_result",
		payload.ClaimRequestID,
		interactionTitleClaimResult,
		summary,
		notification.AppMessageTarget{
			TargetType: "homepage",
			TargetID:   payload.HomepageID,
		},
	), nil
}

func projectHomepageStatusResult(
	event InteractionStreamEvent,
) (*CreateAppMessageCommand, error) {
	var payload struct {
		ReportID          string `json:"reportId"`
		HomepageID        string `json:"homepageId"`
		ReporterPersonaID string `json:"reporterPersonaId"`
		Status            string `json:"status"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode homepage status result payload: %w", err)
	}
	if strings.TrimSpace(payload.ReportID) == "" ||
		strings.TrimSpace(payload.HomepageID) == "" ||
		strings.TrimSpace(payload.ReporterPersonaID) == "" {
		return nil, fmt.Errorf("homepage status result identity is incomplete")
	}
	summary := "你提交的主页状态上报已处理"
	if payload.Status == "confirmed_offline" {
		summary = "你提交的主页状态上报已确认，主页已转为下线记录"
	}
	return interactionCommand(
		event,
		payload.ReporterPersonaID,
		"entity",
		"homepage_status_result",
		payload.ReportID,
		interactionTitleStatusResult,
		summary,
		notification.AppMessageTarget{
			TargetType: "homepage",
			TargetID:   payload.HomepageID,
		},
	), nil
}

func single(command *CreateAppMessageCommand, err error) ([]*CreateAppMessageCommand, error) {
	if err != nil || command == nil {
		return nil, err
	}
	return []*CreateAppMessageCommand{command}, nil
}

func projectReportResult(
	event InteractionStreamEvent,
) (*CreateAppMessageCommand, error) {
	var payload struct {
		ReportID          string `json:"reportId"`
		ReporterAccountID string `json:"reporterAccountId"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode report result payload: %w", err)
	}
	reportID := strings.TrimSpace(payload.ReportID)
	reporterAccountID := strings.TrimSpace(payload.ReporterAccountID)
	if reportID == "" || reporterAccountID == "" {
		return nil, fmt.Errorf("report result identity is incomplete")
	}
	summary := "你提交的举报已处理，可查看最新进度"
	if event.EventType == "content.report.ReportDismissed" {
		summary = "举报审核已完成，暂未发现违规"
	}
	return interactionCommand(
		event,
		reporterAccountID,
		"content",
		"report_result",
		reportID,
		interactionTitleReportResult,
		summary,
		notification.AppMessageTarget{
			TargetType: "report",
			TargetID:   reportID,
		},
	), nil
}

func projectCommentCreated(event InteractionStreamEvent) ([]*CreateAppMessageCommand, error) {
	var payload struct {
		CommentID        string   `json:"commentId"`
		PostID           string   `json:"postId"`
		PostAuthorID     string   `json:"postAuthorId"`
		AuthorID         string   `json:"authorId"`
		ReplyToUserID    string   `json:"replyToUserId"`
		MentionedUserIDs []string `json:"mentionedUserIds"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode CommentCreated payload: %w", err)
	}
	if payload.CommentID == "" || payload.PostID == "" || payload.AuthorID == "" {
		return nil, fmt.Errorf("CommentCreated payload identity is incomplete")
	}
	actorID := strings.TrimSpace(payload.AuthorID)
	commands := make([]*CreateAppMessageCommand, 0, 1+len(payload.MentionedUserIDs))
	notified := map[string]struct{}{actorID: {}}

	recipient := strings.TrimSpace(payload.PostAuthorID)
	title := interactionTitleComment
	summary := "评论了你的作品"
	if reply := strings.TrimSpace(payload.ReplyToUserID); reply != "" {
		recipient = reply
		title = interactionTitleReply
		summary = "回复了你的评论"
	}
	if recipient != "" && recipient != actorID {
		commands = append(commands, interactionCommand(
			event, recipient, "content", "comment", payload.CommentID,
			title, summary, notification.AppMessageTarget{
				TargetType: "post",
				TargetID:   payload.PostID,
			}))
		notified[recipient] = struct{}{}
	}
	// @提及通知：同一评论中已收到评论/回复通知的接收者不重复打扰。
	for _, mentioned := range payload.MentionedUserIDs {
		mentioned = strings.TrimSpace(mentioned)
		if mentioned == "" {
			continue
		}
		if _, already := notified[mentioned]; already {
			continue
		}
		commands = append(commands, interactionCommand(
			event, mentioned, "content", "comment_mention", payload.CommentID,
			interactionTitleMention, "在评论中提到了你", notification.AppMessageTarget{
				TargetType: "post",
				TargetID:   payload.PostID,
			}))
		notified[mentioned] = struct{}{}
	}
	return commands, nil
}

// projectCommentPinChanged 在评论被置顶时通知评论作者；取消置顶不打扰。
func projectCommentPinChanged(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		CommentID       string `json:"commentId"`
		PostID          string `json:"postId"`
		CommentAuthorID string `json:"commentAuthorId"`
		OperatorID      string `json:"operatorId"`
		IsPinned        bool   `json:"isPinned"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode CommentPinChanged payload: %w", err)
	}
	if payload.CommentID == "" || payload.PostID == "" {
		return nil, fmt.Errorf("CommentPinChanged payload identity is incomplete")
	}
	if !payload.IsPinned {
		return nil, nil
	}
	recipient := strings.TrimSpace(payload.CommentAuthorID)
	if recipient == "" || recipient == strings.TrimSpace(payload.OperatorID) {
		return nil, nil
	}
	return interactionCommand(event, recipient, "content", "comment_pin", payload.CommentID,
		interactionTitlePinned, "你的评论被作者置顶了", notification.AppMessageTarget{
			TargetType: "post",
			TargetID:   payload.PostID,
		}), nil
}

func projectReactionSet(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		ReactionID     string `json:"reactionId"`
		TargetKind     string `json:"targetKind"`
		TargetID       string `json:"targetId"`
		TargetAuthorID string `json:"targetAuthorId"`
		ActorDimension string `json:"actorDimension"`
		ActorID        string `json:"actorId"`
		Reaction       string `json:"reaction"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode ContentReactionSet payload: %w", err)
	}
	if payload.ReactionID == "" || payload.TargetID == "" || payload.ActorID == "" {
		return nil, fmt.Errorf("ContentReactionSet payload identity is incomplete")
	}
	// 匿名 device 维度没有可展示的行动者；dislike 不打扰作者。
	if payload.ActorDimension != "persona" || payload.Reaction != "like" {
		return nil, nil
	}
	recipient := strings.TrimSpace(payload.TargetAuthorID)
	if recipient == "" || recipient == strings.TrimSpace(payload.ActorID) {
		return nil, nil
	}
	summary := "赞了你的作品"
	targetType := "post"
	if payload.TargetKind == "comment" {
		summary = "赞了你的评论"
		targetType = "comment"
	}
	return interactionCommand(event, recipient, "content", "reaction", payload.ReactionID,
		interactionTitleLike, summary, notification.AppMessageTarget{
			TargetType: targetType,
			TargetID:   payload.TargetID,
		}), nil
}

func projectQuotedPublish(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		PostID             string `json:"postId"`
		AuthorID           string `json:"authorId"`
		SourcePostID       string `json:"sourcePostId"`
		SourcePostAuthorID string `json:"sourcePostAuthorId"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode PostPublished payload: %w", err)
	}
	// 普通发布不是互动；只有引用发布驱动"被引用"通知。
	if strings.TrimSpace(payload.SourcePostID) == "" {
		return nil, nil
	}
	recipient := strings.TrimSpace(payload.SourcePostAuthorID)
	if recipient == "" || recipient == strings.TrimSpace(payload.AuthorID) {
		return nil, nil
	}
	if payload.PostID == "" {
		return nil, fmt.Errorf("quoted PostPublished payload has no postId")
	}
	return interactionCommand(event, recipient, "content", "post_quote", payload.PostID,
		interactionTitleQuote, "引用了你的作品", notification.AppMessageTarget{
			TargetType: "post",
			TargetID:   payload.PostID,
		}), nil
}

func projectFollowChanged(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	source := strings.TrimSpace(event.Values["sourcePersonaId"])
	target := strings.TrimSpace(event.Values["targetPersonaId"])
	pairID := strings.TrimSpace(event.Values["pairId"])
	if source == "" || target == "" || pairID == "" {
		return nil, fmt.Errorf("PersonaFollowStateChanged event identity is incomplete")
	}
	// 取关不通知；自关注不可能但仍防御跳过。
	if event.Values["following"] != "true" || source == target {
		return nil, nil
	}
	return interactionCommand(event, target, "social", "follow", pairID,
		interactionTitleFollow, "关注了你", notification.AppMessageTarget{
			TargetType: "user",
			TargetID:   source,
		}), nil
}

func projectGreetingSent(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	greetingID := strings.TrimSpace(event.Values["id"])
	requester := strings.TrimSpace(event.Values["requesterPersonaId"])
	target := strings.TrimSpace(event.Values["targetPersonaId"])
	recipientAccountID := strings.TrimSpace(event.Values["recipientAccountId"])
	if greetingID == "" || requester == "" || target == "" || recipientAccountID == "" {
		return nil, fmt.Errorf("GreetingRequestSent event identity is incomplete")
	}
	// side_effects: targetUser.allowStrangerGreeting == true 才投递。
	if event.Values["targetAllowsStrangerGreeting"] != "true" || requester == target {
		return nil, nil
	}
	return interactionCommand(event, recipientAccountID, "social", "greeting", greetingID,
		interactionTitleGreeting, "向你打了个招呼", notification.AppMessageTarget{
			TargetType: "greeting",
			TargetID:   greetingID,
		}), nil
}

func projectCircleJoined(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		ID                   string `json:"id"`
		CircleID             string `json:"circleId"`
		CircleOwnerPersonaID string `json:"circleOwnerPersonaId"`
		PersonaID            string `json:"personaId"`
		State                string `json:"state"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode CircleMembershipJoined payload: %w", err)
	}
	if payload.ID == "" || payload.CircleID == "" || payload.PersonaID == "" {
		return nil, fmt.Errorf("CircleMembershipJoined payload identity is incomplete")
	}
	recipient := strings.TrimSpace(payload.CircleOwnerPersonaID)
	if payload.State != "active" || recipient == "" ||
		recipient == strings.TrimSpace(payload.PersonaID) {
		return nil, nil
	}
	return interactionCommand(event, recipient, "circle", "circle_member", payload.ID,
		interactionTitleCircleJoin, "加入了你的圈子", notification.AppMessageTarget{
			TargetType: "circle",
			TargetID:   payload.CircleID,
		}), nil
}

// projectCircleMembershipDecision 处理圈子级审批双向通知：
// Requested → 通知圈主有新申请；Approved/Rejected → 通知申请人结果。
func projectCircleMembershipDecision(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		ID                   string `json:"id"`
		CircleID             string `json:"circleId"`
		CircleOwnerPersonaID string `json:"circleOwnerPersonaId"`
		PersonaID            string `json:"personaId"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode CircleMembership decision payload: %w", err)
	}
	if payload.ID == "" || payload.CircleID == "" || payload.PersonaID == "" {
		return nil, fmt.Errorf("CircleMembership decision payload identity is incomplete")
	}
	applicant := strings.TrimSpace(payload.PersonaID)
	owner := strings.TrimSpace(payload.CircleOwnerPersonaID)
	if owner == "" || owner == applicant {
		return nil, nil
	}
	recipient := owner
	title := interactionTitleCircleRequest
	summary := "申请加入你的圈子"
	if event.EventType == "CircleMembershipApproved" {
		recipient = applicant
		title = interactionTitleCircleResult
		summary = "你的圈子加入申请已通过"
	} else if event.EventType == "CircleMembershipRejected" {
		recipient = applicant
		title = interactionTitleCircleResult
		summary = "你的圈子加入申请未通过"
	}
	return interactionCommand(event, recipient, "circle", "circle_member_request", payload.ID,
		title, summary, notification.AppMessageTarget{
			TargetType: "circle",
			TargetID:   payload.CircleID,
		}), nil
}

func projectGroupMembership(event InteractionStreamEvent) (*CreateAppMessageCommand, error) {
	var payload struct {
		ID                  string `json:"id"`
		GroupID             string `json:"groupId"`
		GroupOwnerPersonaID string `json:"groupOwnerPersonaId"`
		CircleID            string `json:"circleId"`
		PersonaID           string `json:"personaId"`
	}
	if err := decodeInteractionPayload(event.Payload, &payload); err != nil {
		return nil, fmt.Errorf("decode CircleGroupMembership payload: %w", err)
	}
	if payload.ID == "" || payload.GroupID == "" || payload.PersonaID == "" {
		return nil, fmt.Errorf("CircleGroupMembership payload identity is incomplete")
	}
	applicant := strings.TrimSpace(payload.PersonaID)
	owner := strings.TrimSpace(payload.GroupOwnerPersonaID)
	// 群主自建/自动激活自身成员时不产生任何一侧通知。
	if owner == "" || owner == applicant {
		return nil, nil
	}
	recipient := owner
	title := interactionTitleGroupRequest
	summary := "申请加入群组"
	if event.EventType == "CircleGroupMembershipActivated" {
		recipient = applicant
		title = interactionTitleGroupResult
		summary = "你的群组加入申请已通过"
	}
	if event.EventType == "CircleGroupMembershipRejected" {
		recipient = applicant
		title = interactionTitleGroupResult
		summary = "你的群组加入申请未通过"
	}
	return interactionCommand(event, recipient, "circle", "circle_group", payload.ID,
		title, summary, notification.AppMessageTarget{
			TargetType: "circleGroup",
			TargetID:   payload.GroupID,
		}), nil
}

func interactionCommand(
	event InteractionStreamEvent,
	recipient string,
	messageType string,
	source string,
	sourceID string,
	title string,
	summary string,
	target notification.AppMessageTarget,
) *CreateAppMessageCommand {
	return &CreateAppMessageCommand{
		IdempotencyKey: InteractionNotificationIdempotencyKey(
			event.EventType,
			event.EventID,
			recipient,
			source,
			sourceID,
		),
		UserID:      recipient,
		MessageType: messageType,
		Source:      source,
		SourceID:    sourceID,
		Title:       title,
		Summary:     summary,
		Target:      target,
	}
}

// InteractionNotificationIdempotencyKey 以 event identity + 投递 identity 生成稳定键。
// 同一事件向多个接收者/来源 fan-out 时必须各自唯一；事件重放时又必须收敛到原消息。
// 投递 identity 使用 SHA-256，避免把 recipient 直接暴露在存储键或诊断输出中。
func InteractionNotificationIdempotencyKey(
	eventType string,
	eventID string,
	recipient string,
	source string,
	sourceID string,
) string {
	deliveryIdentity := strings.Join(
		[]string{
			strings.TrimSpace(recipient),
			strings.TrimSpace(source),
			strings.TrimSpace(sourceID),
		},
		"\x1f",
	)
	digest := sha256.Sum256([]byte(deliveryIdentity))
	return "notify:" +
		strings.TrimSpace(eventType) + ":" +
		strings.TrimSpace(eventID) + ":" +
		hex.EncodeToString(digest[:])
}

func decodeInteractionPayload(payload []byte, target any) error {
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if err := decoder.Decode(target); err != nil {
		return err
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return fmt.Errorf("payload contains trailing JSON")
	}
	return nil
}

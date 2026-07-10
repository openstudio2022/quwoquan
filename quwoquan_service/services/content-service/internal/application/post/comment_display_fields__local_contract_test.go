package post

import (
	"context"
	"strings"
	"testing"

	rterr "quwoquan_service/runtime/errors"
)

// authorLiked：内容作者点赞过的评论应在列表投影中标记为 true，其余为 false。
func TestListCommentsDerivesAuthorLiked(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	liked, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_1", "作者会赞我吗", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add liked comment: %v", err)
	}
	likedID, _ := liked["_id"].(string)
	other, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_2", "普通评论", "", "fan_2", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add other comment: %v", err)
	}
	otherID, _ := other["_id"].(string)

	// 内容作者 profile_owner 点赞 fan_1 的评论。
	if _, err := svc.ReactToComment(ctx, likedID, "profile_owner", "like"); err != nil {
		t.Fatalf("author like comment: %v", err)
	}

	items, _, _, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "latest", 20)
	if err != nil {
		t.Fatalf("list comments: %v", err)
	}
	byID := map[string]map[string]any{}
	for _, item := range items {
		byID[asString(item["_id"])] = item
	}
	if got := byID[likedID]; got == nil || asBoolFlexible(got["authorLiked"]) != true {
		t.Fatalf("liked comment must have authorLiked=true: %#v", byID[likedID])
	}
	if got := byID[otherID]; got == nil || asBoolFlexible(got["authorLiked"]) != false {
		t.Fatalf("non-liked comment must have authorLiked=false: %#v", byID[otherID])
	}
}

// ipLocation：创建评论时按受信客户端 IP 解析省级属地落库，读取投影原样透传；
// 无法解析的 IP 留空（不臆造属地）。
func TestAddCommentResolvesIPLocation(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	// 已知 IP 段（确定性 stub 映射 1.2. -> 浙江）。
	knownCtx := WithClientIP(ctx, "1.2.3.4")
	known, _, err := svc.AddComment(
		knownCtx, "post_owner_image", "fan_1", "来自浙江", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add comment with known ip: %v", err)
	}
	if got := strings.TrimSpace(asString(known["ipLocation"])); got != "浙江" {
		t.Fatalf("known ip must resolve to 浙江, got %q", got)
	}

	// 未知 IP：属地留空。
	unknownCtx := WithClientIP(ctx, "203.0.113.7")
	unknown, _, err := svc.AddComment(
		unknownCtx, "post_owner_image", "fan_2", "来自未知", "", "fan_2", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add comment with unknown ip: %v", err)
	}
	if got := strings.TrimSpace(asString(unknown["ipLocation"])); got != "" {
		t.Fatalf("unknown ip must resolve to empty, got %q", got)
	}

	// 读取投影原样透传 ipLocation 快照。
	knownID, _ := known["_id"].(string)
	items, _, _, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "latest", 20)
	if err != nil {
		t.Fatalf("list comments: %v", err)
	}
	for _, item := range items {
		if asString(item["_id"]) == knownID {
			if got := strings.TrimSpace(asString(item["ipLocation"])); got != "浙江" {
				t.Fatalf("projection must carry ipLocation 浙江, got %q", got)
			}
		}
	}
}

// 受信代理头解析优先级：X-Forwarded-For 首段 > X-Real-IP > RemoteAddr。
func TestParseTrustedClientIP(t *testing.T) {
	cases := []struct {
		name       string
		forwarded  string
		realIP     string
		remoteAddr string
		want       string
	}{
		{"xff_first_hop", "1.2.3.4, 9.9.9.9", "", "", "1.2.3.4"},
		{"real_ip_fallback", "", "5.6.7.8", "", "5.6.7.8"},
		{"remote_addr_fallback", "", "", "10.0.0.1:54321", "10.0.0.1"},
		{"invalid_all", "not-an-ip", "", "", ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := ParseTrustedClientIP(tc.forwarded, tc.realIP, tc.remoteAddr); got != tc.want {
				t.Fatalf("ParseTrustedClientIP(%q,%q,%q) = %q, want %q",
					tc.forwarded, tc.realIP, tc.remoteAddr, got, tc.want)
			}
		})
	}
}

// 置顶：仅内容作者可置顶一级评论，置顶项排在列表最前，二级回复不可置顶。
func TestSetCommentPinnedByAuthorPinsAndSortsFirst(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	first, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_1", "第一条评论", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add first comment: %v", err)
	}
	firstID, _ := first["_id"].(string)
	second, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_2", "第二条评论", "", "fan_2", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add second comment: %v", err)
	}
	secondID, _ := second["_id"].(string)

	// 内容作者置顶第二条评论。
	pinned, err := svc.SetCommentPinned(ctx, "post_owner_image", secondID, "profile_owner", true)
	if err != nil {
		t.Fatalf("author pin comment: %v", err)
	}
	if asBoolFlexible(pinned["isPinned"]) != true {
		t.Fatalf("pin projection must report isPinned=true: %#v", pinned)
	}
	if strings.TrimSpace(asString(pinned["pinnedAt"])) == "" {
		t.Fatalf("pin projection must include pinnedAt: %#v", pinned)
	}

	// 默认推荐排序下，置顶评论必须排在最前（即使创建更早的 first 评论）。
	items, _, _, err := svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "", 20)
	if err != nil {
		t.Fatalf("list comments: %v", err)
	}
	if len(items) < 2 {
		t.Fatalf("expected at least 2 comments, got %d", len(items))
	}
	if got := asString(items[0]["_id"]); got != secondID {
		t.Fatalf("pinned comment must be first, got %q want %q", got, secondID)
	}
	if asBoolFlexible(items[0]["isPinned"]) != true {
		t.Fatalf("first item must be pinned: %#v", items[0])
	}

	// 取消置顶后恢复原有排序（first 早于 second）。
	if _, err := svc.SetCommentPinned(ctx, "post_owner_image", secondID, "profile_owner", false); err != nil {
		t.Fatalf("author unpin comment: %v", err)
	}
	items, _, _, err = svc.ListComments(ctx, "post_owner_image", "viewer_x", "", "latest", 20)
	if err != nil {
		t.Fatalf("list comments after unpin: %v", err)
	}
	for _, item := range items {
		if asBoolFlexible(item["isPinned"]) != false {
			t.Fatalf("no comment should remain pinned after unpin: %#v", item)
		}
	}
	_ = firstID
}

// 置顶权限：非内容作者置顶必须返回 CONTENT.USER.comment_pin_forbidden。
func TestSetCommentPinnedForbiddenForNonAuthor(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	c, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_1", "想被置顶", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add comment: %v", err)
	}
	commentID, _ := c["_id"].(string)

	_, err = svc.SetCommentPinned(ctx, "post_owner_image", commentID, "fan_2", true)
	if err == nil {
		t.Fatalf("non-author pin must fail")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected *rterr.AppError, got %T", err)
	}
	if got := appErr.Code.String(); got != "CONTENT.USER.comment_pin_forbidden" {
		t.Fatalf("unexpected error code: %s", got)
	}
}

// canPin：内容作者查看一级评论得到 canPin=true，二级回复及非作者视角均为 false。
func TestListCommentsDerivesCanPin(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	top, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_1", "一级评论", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add top-level comment: %v", err)
	}
	topID, _ := top["_id"].(string)
	if _, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_2", "二级回复", topID, "fan_2", "", nil, nil,
	); err != nil {
		t.Fatalf("add reply: %v", err)
	}

	// 内容作者视角：一级评论 canPin=true，预览中的二级回复 canPin=false。
	authorItems, _, _, err := svc.ListComments(ctx, "post_owner_image", "profile_owner", "", "latest", 20)
	if err != nil {
		t.Fatalf("list as author: %v", err)
	}
	var topItem map[string]any
	for _, item := range authorItems {
		if asString(item["_id"]) == topID {
			topItem = item
		}
	}
	if topItem == nil || asBoolFlexible(topItem["canPin"]) != true {
		t.Fatalf("author must have canPin=true on top-level comment: %#v", topItem)
	}
	if preview, ok := topItem["replyPreview"].([]map[string]any); ok && len(preview) > 0 {
		if asBoolFlexible(preview[0]["canPin"]) != false {
			t.Fatalf("reply must have canPin=false: %#v", preview[0])
		}
	}

	// 非作者视角：canPin=false。
	viewerItems, _, _, err := svc.ListComments(ctx, "post_owner_image", "fan_2", "", "latest", 20)
	if err != nil {
		t.Fatalf("list as viewer: %v", err)
	}
	for _, item := range viewerItems {
		if asBoolFlexible(item["canPin"]) != false {
			t.Fatalf("non-author must have canPin=false: %#v", item)
		}
	}
}

// 置顶约束：二级回复不可置顶，必须返回 CONTENT.USER.comment_pin_invalid_target。
func TestSetCommentPinnedRejectsReply(t *testing.T) {
	ctx := context.Background()
	svc := newProfileInteractionTestService()

	parent, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_1", "一级评论", "", "fan_1", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add parent: %v", err)
	}
	parentID, _ := parent["_id"].(string)
	reply, _, err := svc.AddComment(
		ctx, "post_owner_image", "fan_2", "二级回复", parentID, "fan_2", "", nil, nil,
	)
	if err != nil {
		t.Fatalf("add reply: %v", err)
	}
	replyID, _ := reply["_id"].(string)

	_, err = svc.SetCommentPinned(ctx, "post_owner_image", replyID, "profile_owner", true)
	if err == nil {
		t.Fatalf("pinning a reply must fail")
	}
	appErr, ok := err.(*rterr.AppError)
	if !ok {
		t.Fatalf("expected *rterr.AppError, got %T", err)
	}
	if got := appErr.Code.String(); got != "CONTENT.USER.comment_pin_invalid_target" {
		t.Fatalf("unexpected error code: %s", got)
	}
}

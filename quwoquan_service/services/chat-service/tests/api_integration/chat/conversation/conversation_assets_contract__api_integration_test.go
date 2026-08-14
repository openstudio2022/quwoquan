// 群空间相册/文件宫格的媒体索引读面契约（ListConversationAssets）：
// kind 过滤只回对应类型且交付字段随行；撤回消息不出现在索引；
// keyset 分页游标续接无重复；非法 kind 与非成员按 canonical 失败。
//
// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/spec.md#sit-004
// readiness_case: send-message-api
package api_integration

import (
	"fmt"
	"net/http"
	"testing"
)

func TestConversationAssetsIndexFiltersByKindWithDelivery(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"group space assets"}`)
	convID := conv["id"].(string)

	sendMessage(t, convID, `{"type":"text","content":"文字不进索引","clientMsgId":"assets-text-1"}`)
	image := sendMessage(t, convID, `{"type":"image","content":"","mediaAssetId":"asset-image-101","clientMsgId":"assets-image-1"}`)
	sendMessage(t, convID, `{"type":"file","content":"活动报名表.pdf","mediaAssetId":"asset-file-201","clientMsgId":"assets-file-1"}`)
	recalled := sendMessage(t, convID, `{"type":"image","content":"","mediaAssetId":"asset-image-102","clientMsgId":"assets-image-2"}`)
	doPost(
		t,
		"/chat/conversations/"+convID+"/messages/"+recalled["messageId"].(string)+"/recall",
		`{}`,
		"user_test_001",
		http.StatusOK,
	)

	statusCode, imagePage := doGet(
		t,
		"/chat/conversations/"+convID+"/assets?kind=image&limit=10",
		"user_test_001",
	)
	if statusCode != http.StatusOK {
		t.Fatalf("image assets status = %d body=%#v", statusCode, imagePage)
	}
	imageItems := imagePage["items"].([]any)
	if len(imageItems) != 1 {
		t.Fatalf("recalled image must leave the index, got %d items", len(imageItems))
	}
	imageRow := imageItems[0].(map[string]any)
	if imageRow["messageId"] != image["messageId"] ||
		imageRow["mediaAssetId"] != "asset-image-101" ||
		imageRow["messageType"] != "image" {
		t.Fatalf("image row identity drifted: %#v", imageRow)
	}
	if imageRow["mediaDeliveryUrl"] != "https://media.test/asset-image-101" ||
		imageRow["mediaContentType"] != "image/test" {
		t.Fatalf("image row must carry delivery fields: %#v", imageRow)
	}

	statusCode, filePage := doGet(
		t,
		"/chat/conversations/"+convID+"/assets?kind=file&limit=10",
		"user_test_001",
	)
	if statusCode != http.StatusOK {
		t.Fatalf("file assets status = %d body=%#v", statusCode, filePage)
	}
	fileItems := filePage["items"].([]any)
	if len(fileItems) != 1 {
		t.Fatalf("file index must contain exactly the file message, got %d", len(fileItems))
	}
	fileRow := fileItems[0].(map[string]any)
	if fileRow["fileName"] != "活动报名表.pdf" || fileRow["messageType"] != "file" {
		t.Fatalf("file row must carry display name: %#v", fileRow)
	}
}

func TestConversationAssetsPaginateBySeqWithoutDuplicates(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assets paging"}`)
	convID := conv["id"].(string)
	for index := 1; index <= 5; index++ {
		sendMessage(t, convID, fmt.Sprintf(
			`{"type":"image","content":"","mediaAssetId":"asset-image-page-%d","clientMsgId":"assets-page-%d"}`,
			index, index,
		))
	}

	statusCode, firstPage := doGet(
		t,
		"/chat/conversations/"+convID+"/assets?kind=image&limit=3",
		"user_test_001",
	)
	if statusCode != http.StatusOK {
		t.Fatalf("first page status = %d", statusCode)
	}
	firstItems := firstPage["items"].([]any)
	if len(firstItems) != 3 {
		t.Fatalf("first page size = %d", len(firstItems))
	}
	nextBeforeSeq, ok := firstPage["nextBeforeSeq"].(float64)
	if !ok || nextBeforeSeq <= 0 {
		t.Fatalf("first page must expose nextBeforeSeq: %#v", firstPage)
	}

	statusCode, secondPage := doGet(
		t,
		fmt.Sprintf("/chat/conversations/%s/assets?kind=image&limit=3&beforeSeq=%d", convID, int64(nextBeforeSeq)),
		"user_test_001",
	)
	if statusCode != http.StatusOK {
		t.Fatalf("second page status = %d", statusCode)
	}
	secondItems := secondPage["items"].([]any)
	if len(secondItems) != 2 {
		t.Fatalf("second page size = %d", len(secondItems))
	}
	seen := map[string]bool{}
	lastSeq := int64(1 << 62)
	for _, raw := range append(firstItems, secondItems...) {
		row := raw.(map[string]any)
		id := row["messageId"].(string)
		if seen[id] {
			t.Fatalf("duplicate asset row across pages: %s", id)
		}
		seen[id] = true
		seq := int64(row["seq"].(float64))
		if seq >= lastSeq {
			t.Fatalf("asset rows must stay seq DESC across pages")
		}
		lastSeq = seq
	}
}

func TestConversationAssetsRejectInvalidKindAndNonMember(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	conv := createConversation(t, `{"type":"group","title":"assets guard"}`)
	convID := conv["id"].(string)

	statusCode, failure := doGet(
		t,
		"/chat/conversations/"+convID+"/assets?kind=video",
		"user_test_001",
	)
	if statusCode != http.StatusBadRequest || failure["code"] != "CHAT.USER.invalid_argument" {
		t.Fatalf("invalid kind must map to canonical invalid_argument: status=%d body=%#v", statusCode, failure)
	}

	statusCode, denied := doGet(
		t,
		"/chat/conversations/"+convID+"/assets?kind=image",
		"user_test_999",
	)
	if statusCode != http.StatusNotFound && statusCode != http.StatusForbidden {
		t.Fatalf("non-member must not read the asset index: status=%d body=%#v", statusCode, denied)
	}
}

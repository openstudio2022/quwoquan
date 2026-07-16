package api_integration

import (
	"net/http"
	"testing"

	commentapp "quwoquan_service/services/content-service/internal/application/comment"
)

func TestCommentPinContractApiIntegration(t *testing.T) {
	t.Cleanup(func() { cleanPosts(t) })

	t.Run("post owner pins and unpins a top-level Comment with CAS", func(t *testing.T) {
		cleanPosts(t)
		const postOwner = "pin-post-owner"
		postID := createCommentTestPost(t, postOwner)
		createCommentThroughAPI(t, postID, "commenter-a", "older", "")
		target := createCommentThroughAPI(t, postID, "commenter-b", "pin target", "")

		pinnedRecorder := commentAPIRequest(t, http.MethodPost,
			"/v1/content/posts/"+postID+"/comments/"+target.ID+"/pin",
			postOwner, map[string]any{"version": target.Version})
		if pinnedRecorder.Code != http.StatusOK {
			t.Fatalf("pin Comment status=%d body=%s", pinnedRecorder.Code, pinnedRecorder.Body.String())
		}
		var pinned commentapp.CommentCommandResult
		decodeCommentResponse(t, pinnedRecorder, &pinned)
		if pinned.Version != 2 || pinned.Status != "active" {
			t.Fatalf("unexpected pin result: %+v", pinned)
		}
		page := listCommentsThroughAPI(t, postID, postOwner, "", 20)
		if len(page.Items) != 2 || page.Items[0].ID != target.ID || !page.Items[0].IsPinned {
			t.Fatalf("pinned Comment must lead the page: %+v", page)
		}

		stale := commentAPIRequest(t, http.MethodDelete,
			"/v1/content/posts/"+postID+"/comments/"+target.ID+"/pin",
			postOwner, map[string]any{"version": target.Version})
		if stale.Code != http.StatusConflict {
			t.Fatalf("stale unpin status=%d body=%s", stale.Code, stale.Body.String())
		}
		unpinnedRecorder := commentAPIRequest(t, http.MethodDelete,
			"/v1/content/posts/"+postID+"/comments/"+target.ID+"/pin",
			postOwner, map[string]any{"version": pinned.Version})
		if unpinnedRecorder.Code != http.StatusOK {
			t.Fatalf("unpin Comment status=%d body=%s", unpinnedRecorder.Code, unpinnedRecorder.Body.String())
		}
		var unpinned commentapp.CommentCommandResult
		decodeCommentResponse(t, unpinnedRecorder, &unpinned)
		if unpinned.Version != 3 {
			t.Fatalf("unexpected unpin result: %+v", unpinned)
		}
		page = listCommentsThroughAPI(t, postID, postOwner, "", 20)
		for _, item := range page.Items {
			if item.IsPinned {
				t.Fatalf("unpin must clear all pin state on target: %+v", page)
			}
		}
	})

	t.Run("non-owner and reply pin are rejected", func(t *testing.T) {
		cleanPosts(t)
		const postOwner = "pin-guard-post-owner"
		postID := createCommentTestPost(t, postOwner)
		parent := createCommentThroughAPI(t, postID, "parent-author", "parent", "")

		forbidden := commentAPIRequest(t, http.MethodPost,
			"/v1/content/posts/"+postID+"/comments/"+parent.ID+"/pin",
			"not-post-owner", map[string]any{"version": parent.Version})
		if forbidden.Code != http.StatusForbidden {
			t.Fatalf("non-owner pin status=%d body=%s", forbidden.Code, forbidden.Body.String())
		}

		reply := createCommentThroughAPI(t, postID, "reply-author", "reply", parent.ID)
		invalid := commentAPIRequest(t, http.MethodPost,
			"/v1/content/posts/"+postID+"/comments/"+reply.ID+"/pin",
			postOwner, map[string]any{"version": reply.Version})
		if invalid.Code != http.StatusBadRequest {
			t.Fatalf("reply pin status=%d body=%s", invalid.Code, invalid.Body.String())
		}
	})
}

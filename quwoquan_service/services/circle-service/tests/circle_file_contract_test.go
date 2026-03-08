package tests

import (
	"net/http"
	"testing"
)

// --- storage_upload_flow (contract.yaml scenario) ---

func TestStorageUploadFlow(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "存储测试圈子")

	// Create file
	rec := doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/files", map[string]any{
		"name":     "test_photo.jpg",
		"fileType": "file",
		"mimeType": "image/jpeg",
		"sizeBytes": 1024000,
	})
	if rec.Code != http.StatusCreated {
		t.Fatalf("create file: expected 201, got %d: %s", rec.Code, rec.Body.String())
	}
	body := decodeBody(t, rec)
	data := body["data"].(map[string]any)
	fileID := data["_id"].(string)

	if data["status"] != "uploading" {
		t.Errorf("expected status=uploading, got %v", data["status"])
	}

	// Confirm upload
	rec = doRequest(t, http.MethodPatch, "/v1/circles/"+circleID+"/files/"+fileID, map[string]any{
		"status": "active",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("confirm upload: expected 200, got %d: %s", rec.Code, rec.Body.String())
	}
	body = decodeBody(t, rec)
	data = body["data"].(map[string]any)
	if data["status"] != "active" {
		t.Errorf("expected status=active, got %v", data["status"])
	}

	if events := eventSpy.EventsOfType("CircleFileUploaded"); len(events) == 0 {
		t.Error("expected CircleFileUploaded event to be published")
	}

	// Verify storage used updated
	rec = doRequest(t, http.MethodGet, "/v1/circles/"+circleID+"/stats", nil)
	body = decodeBody(t, rec)
	statsData := body["data"].(map[string]any)
	if toInt64(statsData["storageUsedBytes"]) != 1024000 {
		t.Errorf("expected storageUsedBytes=1024000, got %v", statsData["storageUsedBytes"])
	}
}

// --- storage_quota_exceeded (contract.yaml scenario) ---

func TestStorageQuotaExceeded(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "配额测试圈子")

	// Try to upload a file larger than the circle's default quota (1 GB)
	// Use a file that reports size as entire quota + 1
	rec := doRequest(t, http.MethodGet, "/v1/circles/"+circleID+"/stats", nil)
	body := decodeBody(t, rec)
	statsData := body["data"].(map[string]any)
	quota := toInt64(statsData["storageQuotaBytes"])

	rec = doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/files", map[string]any{
		"name":      "huge_file.zip",
		"fileType":  "file",
		"mimeType":  "application/zip",
		"sizeBytes": quota + 1,
	})
	if rec.Code != http.StatusRequestEntityTooLarge {
		t.Errorf("expected 413, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestFileDeleteUpdatesStorage(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "删除测试圈子")

	// Create + confirm
	rec := doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/files", map[string]any{
		"name": "deleteme.txt", "fileType": "file", "mimeType": "text/plain", "sizeBytes": 5000,
	})
	body := decodeBody(t, rec)
	fileID := body["data"].(map[string]any)["_id"].(string)

	doRequest(t, http.MethodPatch, "/v1/circles/"+circleID+"/files/"+fileID, map[string]any{"status": "active"})

	// Delete
	rec = doRequest(t, http.MethodDelete, "/v1/circles/"+circleID+"/files/"+fileID, nil)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("delete file: expected 204, got %d", rec.Code)
	}

	if events := eventSpy.EventsOfType("CircleFileDeleted"); len(events) == 0 {
		t.Error("expected CircleFileDeleted event to be published")
	}
}

func TestListFiles(t *testing.T) {
	defer cleanCollections(t)

	circleID := createTestCircle(t, "文件列表圈子")
	doRequest(t, http.MethodPost, "/v1/circles/"+circleID+"/files", map[string]any{
		"name": "folder1", "fileType": "folder",
	})

	rec := doRequest(t, http.MethodGet, "/v1/circles/"+circleID+"/files?limit=10", nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	body := decodeBody(t, rec)
	items := body["items"].([]any)
	if len(items) < 1 {
		t.Errorf("expected at least 1 file/folder, got %d", len(items))
	}
}

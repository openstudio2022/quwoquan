package reliabletask

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
)

func dataContentTaskIdentity(job DataContentJob) (map[string]string, error) {
	if _, err := job.ValidateIdentity(); err != nil {
		return nil, err
	}
	return map[string]string{
		"entityRef":      strings.TrimSpace(job.EntityRef),
		"carrier":        strings.TrimSpace(job.Carrier),
		"sourceRevision": strings.TrimSpace(job.SourceRevision),
		"idempotencyKey": strings.TrimSpace(job.IdempotencyKey),
		"jobId":          strings.TrimSpace(job.JobID),
		"executionId":    strings.TrimSpace(job.ExecutionID),
		"ref":            strings.TrimSpace(job.Ref),
		"stage":          strings.TrimSpace(job.Stage),
		"partitionKey":   strings.TrimSpace(job.PartitionKey),
	}, nil
}

// DataContentTaskDigest is byte-compatible with Data canonical JSON hashing.
func DataContentTaskDigest(jobs []DataContentJob) (string, error) {
	rows := make([]map[string]string, 0, len(jobs))
	for _, job := range jobs {
		row, err := dataContentTaskIdentity(job)
		if err != nil {
			return "", err
		}
		rows = append(rows, row)
	}
	if len(rows) == 0 {
		return "", fmt.Errorf("data content task digest requires jobs")
	}
	sort.Slice(rows, func(i, j int) bool {
		return rows[i]["jobId"] < rows[j]["jobId"]
	})
	var buffer bytes.Buffer
	encoder := json.NewEncoder(&buffer)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(rows); err != nil {
		return "", err
	}
	payload := bytes.TrimSuffix(buffer.Bytes(), []byte("\n"))
	digest := sha256.Sum256(payload)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func DataContentAsyncTaskDigest(tasks []ReliableAsyncTask) (string, error) {
	jobs := make([]DataContentJob, 0, len(tasks))
	for _, task := range tasks {
		jobs = append(jobs, DataContentJob{
			EntityRef: task.Payload["entityRef"], Carrier: task.Payload["carrier"],
			SourceRevision: task.Payload["sourceRevision"], JobID: task.Payload["jobId"],
			ExecutionID: task.Payload["executionId"], Ref: task.Payload["ref"],
			Stage: task.Payload["stage"], PartitionKey: task.Payload["partitionKey"],
			IdempotencyKey:       task.Payload["idempotencyKey"],
			JobSetEnvelopeDigest: task.Payload["jobSetEnvelopeDigest"],
			JobSetDigest:         task.Payload["jobSetDigest"],
			ActualTaskDigest:     task.Payload["actualTaskDigest"],
		})
	}
	return DataContentTaskDigest(jobs)
}

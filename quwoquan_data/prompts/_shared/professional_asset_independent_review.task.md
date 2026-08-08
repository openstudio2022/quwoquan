<task>
执行一次独立专业素材准入审阅。
</task>

<documents>
- executionId: `{{execution_id}}`
- objectRef: `{{object_ref}}`
- assetKind: `{{asset_kind}}`
- acquisitionAssetId: `{{asset_id}}`
- acquisitionReceipt: `{{acquisition_receipt_path}}`
- authorEvidence: `{{author_evidence_path}}`
- objectDir: `{{object_dir}}`
- output: `{{output_path}}`
</documents>

读取上述文件及 objectDir 引用的 source evidence，完成独立判断，并将唯一 JSON object 原子写入 output。

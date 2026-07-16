{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 每条写 source_id/platform/url/sourceUseMode 和权利字段。
    - 每个可作为文章底稿的 source 必须带该页面自身可发布的 imageUrls（含 license/credit/termsUrl/licenseSnapshot/authorizationProof/usageScope/width/height/relevance），源图是文章底稿的一部分。
    - sourceUseMode 是文字来源权利模式，不是图片许可。
    - imageUrls[].license 必须是明确图片许可或授权类型（如 CC BY-SA 4.0、CC BY 4.0、Public domain、photographer_authorized、scenic_official_authorized 等），否则替换整条 source unit 或换同源可授权图片。
    - 实际图片必须可下载，宽≥640、高≥426、长边≥800。
  </always>
  <never>
    - imageUrls[].license 严禁填写 factual_reference_only/licensed_adaptation/blocked。
    - 禁止使用 r_720x480、600x600、缩略图、平台压缩图或无独立授权证明的图片。
    - 不得复用 homepage 计划 URL，不得读取或修改 image 计划。
  </never>
</constraints>

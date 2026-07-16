{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 至少保留 2 个真实可抓取来源。普通网页一律 factual_reference_only；只有明确许可才能 licensed_adaptation。
    - 主页图片必须来自这些主页来源自身的 imageUrls，逐图填写许可、署名、条款、授权快照、usageScope、width、height 和具体相关性。
    - 实际图片必须可下载，宽≥640、高≥426、长边≥800，不要使用缩略图/压缩图/探针图。
  </always>
  <never>
    - 不得读取或修改 article/image 计划。
  </never>
</constraints>

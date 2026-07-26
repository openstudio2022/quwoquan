{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 输出 collections；每组必须有 sourceCollectionId、creator、collectionPageUrl 和 images；逐图尽可能保留 license、termsUrl、licenseSnapshot、authorizationProof、usageScope。
    - 按运行时提供的 rightsEnforcementMode 决策：audit_only 必须如实记录授权缺口但不得过滤素材，enforce 才要求完整许可或授权证明。
    - 每张图必须填写 width/height，实际可下载，宽≥640、高≥426、长边≥800，并直接呈现该景区。
    - 每个作品可选同一集合内 1..20 张。
  </always>
  <never>
    - 严禁使用 factual_reference_only/licensed_adaptation/blocked 这类 sourceUseMode 名称冒充图片许可。
    - 禁止跨作者/页面/专辑/授权凭证混图。
    - 不得读取或修改 homepage/article 计划。
  </never>
</constraints>

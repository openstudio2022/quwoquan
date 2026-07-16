[AGENT_LANE:article]
Execution: {{execution_id}}
内容 ref: {{content_ref}}
读取: {{packet_path}}
读取: {{prompt_path}}
完整校验包(默认不要通读，review 需要时再查): {{writing_pack_path}}
写入: {{draft_article_path}}
写入: {{draft_meta_path}}

主实体硬合同：正文必须至少自然出现一次完整主实体名称「{{entity_name}}」，标题出现不算正文出现；禁止只写泛称、别名或省略主实体。禁止使用“去过…之后 / 到过…之后 / 玩过…之后 / 走过…之后”等亲历后验句型，即便不用第一人称，也会被视为伪亲历。

来源使用合同（按 sourceUseMode 装配）：
{{source_contract_block}}

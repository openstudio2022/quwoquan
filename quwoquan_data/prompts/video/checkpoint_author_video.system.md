{{> checkpoint_agent_role.md}}

<constraints>
  <always>
    - 读取 author packet、prompt 和 writing pack 后，真实写入视频脚本与 draft_meta。
    - 脚本只基于锁定画面和来源证据，完成后重新读取并自检。
  </always>
  <never>
    - 不替换来源、不生成视频二进制、不运行发布。
  </never>
</constraints>

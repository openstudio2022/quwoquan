"""render_prod_plane_stack 的实现子包。

唯一稳定入口是 ``quwoquan_ops/cli/prod/render_prod_plane_stack.py``；
该薄入口保留被 gate 源码文本扫描钉住的 ``_rewrite_service`` /
``_write_config_tree`` / ``_write_caddyfile``，并 re-export 本包全部符号。
本包按职责切分：

- ``constants``：渲染面共享常量（外部数据端口、日志导出服务集合等）。
- ``package_inputs``：CLI 参数与发布包/配置输入校验、预检密钥材料。
- ``volume_layout``：compose 卷与运行时凭据挂载重写。
- ``public_hosts``：生产公网域名解析与灰度路由块。
- ``runtime_outputs``：stack.env / systemd unit / observability 渲染落盘。
- ``render_entry``：main 装配流程。

子模块之间只做包内相对导入；需要回访入口模块属性（monkeypatch 目标）
时一律在函数体内延迟导入，避免初始化环。
"""

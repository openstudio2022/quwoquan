# Contract Scenario Fixtures

`test_fixtures` 只保存 `local_contract` 与 `api_integration` 测试树使用的最小媒体样本与对象级 typed double 资产。它不参与环境 package、runtime bootstrap 或 user_acceptance 数据供给。

## 环境约定

- `local_contract` / `api_integration`：测试树内对象级 typed double 可读取测试资产。
- `alpha` / `beta` / `gamma`：内容由 canonical immutable release 激活；账号、评论、圈子、会话和消息由 `stackctl verify` 使用真实非生产主体调用公开 command/event 创建。
- `prod`：不包含或读取本目录，也不执行任何 nonprod provision runner。

## 资产约定

- 对象级输入由测试语言自身的 typed builder/generator 构造，不在本目录维护场景 dump 或环境数据源选择。
- 仅在解码、媒体处理等确需字节样本时保存最小文件，并由测试直接声明业务断言。
- 大规模评测数据使用独立 corpus + manifest + digest；环境交易事实继续由所属领域公开 command/event 创建。

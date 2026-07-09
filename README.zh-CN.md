# Gokumoku

Gokumoku 是一个面向实战的混合架构五子棋引擎。结合先手证明数据、通用强搜索和白棋防守决策层。项目同时提供了浏览器对弈界面、自动化对战框架和终端仪表盘（TUI），方便人类对弈、本地评测和迭代调优。

## 引擎架构

Gokumoku 对黑棋和白棋采用不同的决策策略，因为二者面对的问题本质上不同。

**黑棋**结合了两类能力：一类来自先手必胜证明项目中的证明数据库，可以在覆盖到的局面里给出精确的必胜延续；另一类来自通用搜索引擎，可以在自摆残局等脱离证明树的局面下继续给出计算上几乎最佳的实战落子。两套来源的切换对前端透明，API 会标明当前活跃的黑棋引擎。

**白棋**是 Gokumoku 自有的防守决策层：它拥有由大量历史自对弈与多引擎相互对局沉淀出的经验应对库。它会优先检查当前局面的直接胜负手，使用 Rapfi 等强引擎对候选落点做局部搜索评估，在可用时参考多个 Gomocup 兼容引擎的建议。白棋的目标被设定为是尽可能延长抵抗、在黑棋偏离证明路线时尽可能抓住失误，在出现战术机会时主动反击。

## 功能

- 浏览器棋盘，支持手动摆盘、机器执黑、机器执白、悔棋、重新开始和胜负判断。
- `/next_step`：黑棋接口。
- `/white_next_step`：白棋接口。
- 黑棋会根据局面选择证明数据或强搜索引擎。
- 白棋可以接入 Rapfi 和多个 Gomocup 兼容引擎来提升决策质量。
- 附带本地引擎对战与评估工具。
- 支持通过局域网代理从其他设备访问棋盘。

## 本地运行

安装依赖：

```bash
python -m pip install -r requirements.txt
```

创建本地配置：

```bash
cp .env.example .env
```

在 `.env` 里配置证明数据、Rapfi 和可选 Gomocup 引擎路径。

启动服务：

```bash
cd server
python white_ai_server.py 8090
```

打开：

```text
http://127.0.0.1:8090/gomoku.html
```

如果想让局域网里的其他设备访问：

```bash
node tools/lan_proxy.js --listen-host=<你的局域网IP> --listen-port=8090 --target-host=127.0.0.1 --target-port=8090
```

## 外部资源

本仓库为干净发布仓库，不打包大型引擎二进制文件、神经网络权重、LevelDB 证明数据库或原始 benchmark 日志。

要复现完整强度，需自行准备：

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win) 中的先手必胜证明数据和 LevelDB 文件，以及对应的 `web_search` 二进制（用于证明搜索 fallback）
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi) 可执行文件与网络权重
- 可选的 Gomocup 兼容 PBrain 引擎目录（置于 `GOMOCUP_ENGINE_ROOT` 下）

缺少这些资源时，网页仍可正常打开和对弈，但 AI 强度不会等同于上述实验结果。

## 致谢

Gokumoku 基于并整合了以下项目或生态中的思路与组件：

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) 及其 AI 生态
- jQuery

许可证和再分发说明见 [NOTICE.md](NOTICE.md)。

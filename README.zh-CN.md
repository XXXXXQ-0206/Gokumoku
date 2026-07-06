# Gokumoku

Gokumoku 是一个实验性的高强度五子棋 AI 项目，核心目标有两个：

- 在黑棋仍处于 fucusy 已证明先手必胜路径时，保持原项目黑棋行为
- 通过最长抵抗谱、Rapfi 分析、Gomocup 老师投票和 calculator 风格战术路由，构建更强的白棋防守 AI

这是一个研究型系统，不是把所有大型引擎、网络权重、证明数据库和原始优化日志都打包进去的发行包。干净仓库默认不包含大型第三方引擎、fucusy 证明数据和本地优化残留。

## 包含内容

- Tornado Web 服务：
  - `/next_step`：黑棋
  - `/white_next_step`：白棋
  - `/gomoku.html`：前端页面
- 改造后的五子棋网页前端，支持手动摆盘、机器执黑、机器执白、悔棋、重新开始、终局判断和精简诊断表。
- 公开测试/benchmark 辅助工具。
- fucusy、Rapfi、Gomocup 引擎路径配置样例。

## 当前本地结果

以下是本地实验结果，不是 Gomocup 官方排名或官方 Elo。

| 场景 | 设置 | 结果 |
|---|---:|---|
| fucusy 黑棋一致性 | `_h8_a1`，高等级 | 黑棋从 LevelDB 返回 `i9` |
| calculator/Rapfi 黑棋 vs calculator 路线白棋 | depth 64，4 线程，5000 ms/手 | BLACK/21 |
| calculator/Rapfi 黑棋 vs 当前 auto 白棋 | depth 64，4 线程，5000 ms/手 | BLACK/33 |
| 本地 14 引擎单轮 | depth 4，1 线程，500 ms/手 | 8W-1D-5L |
| 本地 11 引擎验收单轮 | depth 4，1 线程，500 ms/手 | 5W-0D-6L |

项目目标是追赶公开五子棋 AI 的近前沿强度，但目前不能宣称已经获得 Gomocup 官方第一，也不能宣称稳定不败于所有公开引擎。

## 运行

安装 Python 依赖：

```bash
python -m pip install -r requirements.txt
```

配置外部引擎和数据：

```bash
cp .env.example .env
```

在 shell 中导出 `.env` 内的变量，或手动设置对应环境变量。

启动服务：

```bash
cd server
python white_ai_server.py 8090
```

打开：

```text
http://127.0.0.1:8090/gomoku.html
```

如果要发到局域网，可以使用正式反向代理，也可以用辅助脚本：

```bash
node tools/lan_proxy.js --listen-host=<你的局域网IP> --listen-port=8090 --target-host=127.0.0.1 --target-port=8090
```

## 外部资产

满血强度需要你自行提供：

- fucusy LevelDB/证明数据，放在 `server/leveldb.db` 或通过配置指定
- fucusy `web_search` 二进制，用于复现原项目搜索 fallback
- Rapfi 可执行文件和网络权重
- 可选的 Gomocup PBrain 引擎目录

缺少这些资产时，网页仍可打开，但 AI 强度不会等同于上面的实验结果。

## 致谢

Gokumoku 基于并参考了：

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) 及其 AI 生态
- jQuery

许可证和再分发说明见 [NOTICE.md](NOTICE.md)。

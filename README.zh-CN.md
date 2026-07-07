# Gokumoku

Gokumoku 是一个可以直接在网页上下棋的五子棋 AI 项目。它不是单一引擎的简单套壳，而是把证明型黑棋、通用强搜索引擎和经过本地对战调校的白棋防守系统组织到同一套对局服务里。

这个项目的目标很直接：让你能在浏览器里和一个足够强、足够有研究价值的五子棋 AI 对弈，同时也能把它拿去和 Gomocup 级别的引擎做本地测试。

## 设计思路

Gokumoku 对黑棋和白棋采用不同策略，因为二者面对的问题并不一样。

黑棋部分结合了两类能力：一类来自先手必胜证明项目中的证明数据库，可以在覆盖到的局面里给出精确的必胜延续；另一类来自通用搜索引擎，可以在局面脱离证明树时继续给出高强度实战落子。这样黑棋既能利用已证明路线，也不会在异常天元、残局摆盘或数据库未覆盖局面里卡住。

白棋部分是 Gokumoku 自己的防守决策层。它会优先检查直接胜负手，使用 Rapfi 这类强引擎做局部判断，在可用时参考多个 Gomocup 兼容引擎的建议，并结合本地大量引擎对局中表现更好的应对路线。它的目标不是机械地挡棋，而是在黑棋偏离证明路线时尽可能延长抵抗、抓住失误，并在出现战术机会时主动反击。

## 功能

- 浏览器棋盘，支持手动摆盘、机器执黑、机器执白、悔棋、重新开始和胜负判断。
- `/next_step`：黑棋接口。
- `/white_next_step`：白棋接口。
- 黑棋会根据局面选择证明数据或强搜索引擎。
- 白棋可以接入 Rapfi 和多个 Gomocup 兼容引擎来提升决策质量。
- 附带本地引擎对战与评估工具。
- 支持通过局域网代理从其他设备访问棋盘。

## 本地结果

下面是本地实验结果，不是 Gomocup 官方排名，也不是官方 Elo。

| 测试 | 设置 | 结果 |
|---|---:|---|
| 证明库黑棋一致性检查 | `_h8_a1`，高等级 | 黑棋从 LevelDB 返回 `i9` |
| calculator/Rapfi 黑棋 vs calculator 路线白棋 | depth 64，4 线程，5000 ms/手 | BLACK/21 |
| calculator/Rapfi 黑棋 vs Gokumoku auto 白棋 | depth 64，4 线程，5000 ms/手 | BLACK/33 |
| 本地 14 引擎单轮测试 | depth 4，1 线程，500 ms/手 | 8W-1D-5L |
| 本地 11 引擎验收测试 | depth 4，1 线程，500 ms/手 | 5W-0D-6L |

Gokumoku 的目标是接近公开五子棋 AI 的高强度水平，但上面的数据只是本地可复现实验记录，不应当当作官方排名。

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

这个干净仓库不打包大型引擎、神经网络权重、证明数据库或原始 benchmark 日志。

如果要达到完整强度，需要自行准备：

- `fucusy/gomoku-first-move-always-win` 中的先手必胜证明数据和 LevelDB 文件
- 如果需要完整复现证明搜索 fallback，还需要对应的 `web_search` 二进制
- Rapfi 可执行文件和网络权重
- 可选的 Gomocup 兼容 PBrain 引擎目录

缺少这些资源时，网页仍然可以打开，但 AI 强度不会等同于上面的实验结果。

## 致谢

Gokumoku 基于并整合了以下项目或生态中的思路与组件：

- [fucusy/gomoku-first-move-always-win](https://github.com/fucusy/gomoku-first-move-always-win)
- [dhbloo/gomoku-calculator](https://github.com/dhbloo/gomoku-calculator)
- [dhbloo/rapfi](https://github.com/dhbloo/rapfi)
- [Gomocup](https://gomocup.org/) 及其 AI 生态
- jQuery

许可证和再分发说明见 [NOTICE.md](NOTICE.md)。

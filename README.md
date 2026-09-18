# SeatBond

影院连座锁座：按场次厅图查找连续空座，过道列断开，冲突检测既有持座。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4100 |
| API | http://localhost:9100 |
| API 文档 | http://localhost:9100/docs |
| Postgres | localhost:5442 |

健康检查：`GET http://localhost:9100/api/health`

## 页面

- `/halls` — 影厅
- `/showtimes` — 场次
- `/seatmap` — 座位图（大网格热力）
- `/hold` — 锁座
- `/orders` — 订单
- `/conflicts` — 冲突（原因码筛选与启停）

## 冲突原因码

锁座失败写入冲突日志时，除可读说明外携带稳定 `reason_code`。目录预置：连续空座不足、与既有持座重叠、半对情侣、遮挡禁锁、跨过道非法、未归类（后几项业务未全开时码已就绪）。

- `GET /api/conflict-reasons` — 查询代码、中文说明、是否建议重试、是否启用
- `PATCH /api/conflict-reasons/{code}` — 启用/停用，body：`{"enabled": false}`
- `GET /api/conflicts?reason_code=XXX` — 按码筛选冲突日志

## 使用说明

1. 在影厅与场次页确认厅图与排期。
2. 打开座位图查看占用热力，在锁座页输入连座人数并提交。
3. 订单页查看持座结果；冲突页查看重叠请求。

## 开发与测试

```bash
docker compose exec api pytest -q
```

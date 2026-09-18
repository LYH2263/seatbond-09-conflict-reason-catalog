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
- `/conflicts` — 冲突

## 使用说明

1. 在影厅与场次页确认厅图与排期。
2. 打开座位图查看占用热力，在锁座页输入连座人数并提交。
3. 订单页查看持座结果；冲突页查看重叠请求。

## 冲突原因码

锁座失败写入冲突日志时必带稳定 `reason_code`（另保留人读 `reason`），由原因码目录维护中文说明、是否建议重试、是否启用：

| 代码 | 含义 | 建议重试 |
| --- | --- | --- |
| `NO_CONTIGUOUS_SEATS` | 连续空座不足 | 是 |
| `OVERLAP_EXISTING_HOLD` | 与既有持座重叠 | 是 |
| `COUPLE_PAIR_SPLIT` | 半对情侣（模块未全开，目录先就绪） | 是 |
| `OBSTRUCTED_VIEW` | 遮挡禁锁（模块未全开，目录先就绪） | 否 |
| `AISLE_CROSSING` | 跨过道非法（模块未全开，目录先就绪） | 否 |
| `UNCLASSIFIED` | 未归类兜底 | 否 |

- `GET /api/reason-codes`（`?active_only=true` 仅启用码）、`PATCH /api/reason-codes/{code}` 启停/维护。
- `GET /api/conflicts?reason_code=...` 按码筛选；停用码的历史日志仍可查出。
- 冲突页同页可查看“代码+说明”、按码筛选，并在简易目录面板中启用/停用。

## 开发与测试

```bash
docker compose exec api pytest -q
```

# 公交刷卡换乘优惠与日封顶回算

供公交清分中心复核员核对原始记录、处理差异并封存证据。

## 启动

```sh
docker compose up --build -d
docker compose exec -T app pytest -q
```

打开 http://localhost:18245 。首次进入自动运行仓内脏样例。工具条可重跑、切换样例或上传CSV。SQLite保存在命名卷records中，重建服务保留批次。

## 模块

- 1. 刷卡采信：`/taps`，`/api/taps`。
- 2. 线路换乘：`/routes`，`/api/routes`。
- 3. 票价版本：`/fares`，`/api/fares`。
- 4. 行程配对：`/journeys`，`/api/journeys`。
- 5. 优惠回算：`/discounts`，`/api/discounts`。
- 6. 清分对账：`/clearing`，`/api/clearing`。
- 7. 日结归档：`/settlement`，`/api/settlement`。

## 核心规则

换乘按上次有效付费行程的时间窗计算，优惠与日封顶按确定顺序裁决并保留分币守恒。

月末文件超过4MB时按字节分块上传（`POST /api/sources/<source>/parts/<n>`），收齐后 `POST /api/sources/<source>/finalize`。**裁决：分块只作传输边界，不跨块接续卡日状态；计算前对同一来源按「卡号+业务日」重新归集，再统一裁决换乘与六元封顶。** 因此分块顺序、重试与补块不影响结果，与整包上传逐行一致。

- 同一来源重试幂等：同块同摘要只刷新收块时间，不新增批次；同块不同内容返回409并保留原始分块。
- 处理中断不落库，上一完整旧版与复核状态保留。
- 每条来源记录必须有唯一去向（采纳/隔离/重复/空白/分段表头）；去向不完整时不允许封存，证据导出返回409。
- 原始刷卡分块与来源摘要保存在SQLite，结算后仍可复核与重算。

## 批次复核

`/batches` 沿超限日批列出每个来源的分块收齐情况，并展开每个「卡号+业务日」的凭证、换乘依据、封顶依据、处理位置与逐事件明细。`/discounts` 与首页同样显示卡日结算；顶栏「卡日结算」导出可发布的卡日 CSV（含合计），「导出证据」导出逐条来源去向 CSV。

## 演示

1. 打开首页，核对当次计算、差异和隔离原因。
2. 切换模块查看源行及裁决依据。
3. 重跑相同样例，批次号与行数保持一致。
4. 复核后导出一份证据CSV。版本已变化的复核提交返回409。

## 输入与输出

输入列见 `docs/DATA-DICTIONARY.md`。项目包含dirty.csv、clean.csv、legacy.csv，统一走实际导入路径。单块上传限制4MB，拒绝不带时区的时间。业务键按字符串保留，Decimal参与计算，空值不会当零。

`POST /api/runs` 接收sample或csv；`GET /api/runs`返回历史批次；`POST /api/runs/<id>/review`需要version与decision；`GET /api/runs/<id>/archive`返回唯一证据导出。

## 范围

样例均为虚构。单机复核工具不连接生产系统；不提供登录、远端数据库或自动支付。内存计算按单块4MB、单来源64MB上限控制，SQLite事务与「算完才落库」保证只写入完整结果。

## 目录

app为服务与规则，sample_data为输入，tests为测试，docs为定义与深度登记。

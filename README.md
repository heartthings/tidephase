# 观势数据层 (market-datalayer)

> 自建时序库（TimescaleDB）+ 采集管道 + data-api + 观势台页面

## 架构

```
数据源（腾讯/东财/通达信/AKShare/新浪/龙虎/…）
    ↓
dsched 调度服务（APScheduler + job_registry）
    ↓
dworker 采集工作器（源适配器 + 降级链 + 校验 + quarantine）
    ↓
TimescaleDB (PG16) · market_tsdb
    ↓
data-api (FastAPI，容器内 8787，宿主仅 127.0.0.1:8787)
    ↓
观势台 market-console（127.0.0.1:7511）
    · 静态页面
    · /api、/auth 同源转到 market-api
    · frp [console]：本机 7511 → 公网 8005（原来系统 nginx 的映射）
    ↓
浏览器 / 观势 skill
```

页面容器自带 nginx，只服务观势台。宿主机不再跑系统 nginx；每个应用自己占一个本机端口，再在 frp 里单独转发。

## 目录结构

```
market-datalayer/
├── console/                  # 观势台（guanshi-console）
├── db/migrations/            # DDL 迁移（V001__init...）
├── dworker/                  # 采集框架
│   ├── adapters/             # 源适配器（tencent/eastmoney/mootdx/akshare/sina）
│   ├── core/                 # 降级链/限速/重试/校验/quarantine
│   └── validate/             # 校验引擎
├── dsched/                   # 调度服务
├── data_api/                 # FastAPI
├── tools/                    # 迁移/回填/冒烟工具
├── ops/                      # docker-compose
├── configs/                  # rate_limits / validation_rules / secrets（不入 git）
├── tests/                    # 单元测试
├── data/raw/                 # raw 归档（不入 git）
└── reports/                  # 施工报告
```

## 快速启动

```bash
# 1. 配置凭证
cp configs/secrets.yaml.example configs/secrets.yaml
# 编辑 secrets.yaml 填入密码

# 2. 启动服务
cd ops && docker compose up -d

# 3. 运行迁移
python3 tools/migrate.py --host 127.0.0.1 --port 15432 --user postgres --password <super_pw>

# 4. 验证
docker compose ps
```

## 角色权限

| 角色 | 权限 | 用途 |
|------|------|------|
| duser_writer | SELECT/INSERT/UPDATE 采集表 | 采集管道 |
| duser_reader | SELECT + statement_timeout=30s | data-api 查询 |
| duser_admin | ALL | 运维/DDL |
| duser_d12writer | cognition/prediction/base_rate INSERT/UPDATE | D12 写通道 |

## 安全红线

- 凭证/密码/token 一律不进 git（secrets.yaml + .gitignore）
- 监听端口只绑 127.0.0.1（或 compose 内网）
- 不动生产容器
- API 永不公网暴露

## 运维决策记录

| 日期 | 决策 | 说明 |
|------|------|------|
| 2026-10-10 | **取消 dops 远端备份** | 梁总裁决：不需要备份。风险告知已由督军留痕。代码面不建 backup timer/脚本。 |

## 状态

- **Z1 波**：数据层基建 ✅ 完成
- **Z2 波**：data-api 实装 + 龙虎 adapter ✅ 完成
- **Z7 波**：数据纠错 + 龙虎落地 + Z5 残余（进行中）

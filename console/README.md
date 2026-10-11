# 观势台（guanshi-console）

观势数据层的页面。容器名 `market-console`，只监听 `127.0.0.1:7511`。

frp 段 `[console]` 把本机 7511 转到公网 8005，这是原来系统 nginx 的映射。`/api` 和 `/auth` 由容器内 nginx 转到 `market-api:8787`，浏览器走同源，8787 不暴露到公网。

```bash
cd ops && docker compose up -d --build market-console
```

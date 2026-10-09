# 好价雷达无桌面容器

上游基线：archie96211/smzdm @ f96fd7a5449f003bc93d3787006ce1d91fe1431b。

启动：在 compose.yaml 所在目录执行 `docker compose up -d --build`。
`.env` 设置 `SMZDM_BIND_IP=你的内网IP`、`SMZDM_PORT=18085`；更换网段时设置
`SMZDM_ALLOWED_NETWORKS=你的内网CIDR`。默认只绑定本机。
这是可信局域网管理界面，无账号认证，勿映射到公网。

资源上限：0.5 CPU、256 MiB 内存（禁用额外 swap）、64 PID。
非 root、只读根文件系统；SQLite 用命名卷，日志轮转总量约 6 MB。
不安装桌面 GUI、Node、浏览器或微信桥接；钉钉/WxPusher 代码保留，但需用户配置。
原前端资源直接随容器提供。

上游 API 仅用于读取公开优惠列表，依赖其可用性；不代表账号实际结算价。
每个关键词每轮读取最新 20 条，高频品类可能漏掉轮询间隔内超出 20 条的爆料。
历史数据目前保留全部，长期运行需关注数据卷增量，软路由宜使用外置持久化存储。

健康接口 `/api/health` 只证明服务存活；`/api/metrics` 提供本次启动以来的采集结果。
正常空结果和接口失败分开记录；接口失败按关键词退避 60 秒至 1 小时。
轮询下限 60 秒，建议少量关键词使用 300 秒。重启不会删除 SQLite 历史。

验证：安装 requirements-server.txt 和 httpx==0.28.1 后，运行
`python -m unittest discover -s tests -p '*checks.py' -v`。
占用测量：在宿主机运行 `python3 deployment/observe.py --seconds 330 --out observation.jsonl`。
该脚本访问 Docker socket，应仅由已有 Docker 管理权限的用户运行。

停止：`docker compose stop`。卸载容器：`docker compose down`（保留数据卷）。
不要加 `-v`，除非明确希望删除监控历史。

`.35` 特殊情况：默认 docker0 缺失，首次构建使用
`docker build --network=host -t smzdm-headless:local .`，随后 `docker compose up -d --no-build`。
不修改宿主 Docker 全局配置，也不重启其他服务。

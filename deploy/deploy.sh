#!/usr/bin/env bash
# 一键部署/更新到服务器（只动 /opt/aten 与 nginx 的 aten 站点文件）。
#   SSH_HOST=root@1.2.3.4 DOMAIN=aten.example.com deploy/deploy.sh
# 首次部署前在服务器 /opt/aten/.env 填好密钥（参考 .env.example），本脚本不会上传或覆盖 .env。
set -euo pipefail
cd "$(dirname "$0")/.."
: "${SSH_HOST:?需要 SSH_HOST}" "${DOMAIN:?需要 DOMAIN}"
APP=/opt/aten

(cd web && npm ci && npm run build)
rsync -az --delete \
  --exclude .env --exclude '.git' --exclude 'web/node_modules' --exclude 'web/src' \
  --exclude 'user_data/data' --exclude 'user_data/*.sqlite*' --exclude 'user_data/logs/*' \
  --exclude 'user_data/backtest_results' --exclude 'user_data/hyperopt_results' \
  ./ "$SSH_HOST:$APP/"
ssh "$SSH_HOST" "set -e; cd $APP
  test -f .env || { echo '缺少 $APP/.env，先按 .env.example 创建'; exit 1; }
  sed 's/aten.example.com/$DOMAIN/g' deploy/nginx/aten.conf > /etc/nginx/conf.d/aten.conf
  nginx -t && systemctl reload nginx
  docker compose -p aten -f deploy/docker-compose.prod.yml up -d --remove-orphans
  docker compose -p aten -f deploy/docker-compose.prod.yml ps"

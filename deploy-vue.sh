#!/usr/bin/env bash
# Build the fork's Vue frontend into a fresh image and deploy it.
# usage: deploy-vue.sh <tag-number>   e.g. deploy-vue.sh 41
set -euo pipefail
TAG=${1:?usage: deploy-vue.sh <tag-number>}
BASE=/home/daniel/projects/tandoor
REPO=$BASE/tandoor-ui
IMG=atlas-tandoor:2.7.8-kitchen-v$TAG

cd "$REPO"
npm --prefix vue3 run build >/tmp/vue-build.log 2>&1 || { echo "BUILD FAILED"; tail -30 /tmp/vue-build.log; exit 1; }
tail -3 /tmp/vue-build.log

# a clean context: HEAD plus this working tree's vue sources only, so a sibling
# worker's uncommitted backend edits never sneak into the image
rm -rf "$BASE/build-$TAG"; mkdir -p "$BASE/build-$TAG"
git archive HEAD | tar -x -C "$BASE/build-$TAG"
cp -a vue3/src/. "$BASE/build-$TAG/vue3/src/"
mkdir -p "$BASE/build-$TAG/cookbook/static"
cp -a cookbook/static/vue3 "$BASE/build-$TAG/cookbook/static/"

cd "$BASE/build-$TAG"
docker build --pull=false -t "$IMG" . | tail -2

python3 - "$TAG" <<'PY'
import re, sys
tag = sys.argv[1]
p = '/opt/atlas/compose/tandoor/compose.yml'
s = open(p).read()
new, n = re.subn(r'atlas-tandoor:2\.7\.8-kitchen-v\d+', f'atlas-tandoor:2.7.8-kitchen-v{tag}', s)
assert n == 1, f'expected one image line, found {n}'
open(p, 'w').write(new)
print('compose ->', re.search(r'atlas-tandoor:\S+', new).group(0))
PY

cd /opt/atlas
ATLAS_DEPLOY_ALLOW_PULL_FAILURE=true ./atlasctl deploy tandoor >/tmp/deploy.log 2>&1 || true
sleep 25
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' | grep tandoor-recipes

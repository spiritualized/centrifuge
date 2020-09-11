#!/usr/bin/env bash
APP_NAME="centrifuge"
APP_PLATFORM="linux"

cd /
git clone https://github.com/spiritualized/centrifuge.git
cd /centrifuge
pip3 install -r requirements.txt

pyinstaller 	--additional-hooks-dir "hooks" \
				--add-data "ini_template:." \
				--hidden-import=_sqlite3 \
				centrifuge.py

VERSION=`git describe --tags`
FOLDER_NAME="$APP_NAME-$VERSION-$APP_PLATFORM"
mv dist/centrifuge "dist/$FOLDER_NAME"
env GZIP=-9 tar cvzf "/releases/$FOLDER_NAME.tar.gz" -C dist "$FOLDER_NAME"

rm -R /centrifuge

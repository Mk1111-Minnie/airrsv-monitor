# Airリザーブ空き監視

指定したAirリザーブの予約ページを10分おきに確認し、対象日に予約可能な時間が見つかった場合だけntfyでiPhoneへ通知します。

## 対象日

`monitor.py` の `TARGET_DATES` を変更できます。

現在は:
- 2026-11-13
- 2026-11-14

## iPhone通知（ntfy）

1. iPhoneに「ntfy」アプリをインストール
2. アプリで自分だけが使うランダムなTopic名を決める
   - 例: `mayuko-air-9f3k2x7p`
   - 推測されにくい文字列にしてください
3. GitHubリポジトリの Settings → Secrets and variables → Actions → New repository secret
4. Name: `NTFY_TOPIC`
5. Value: 2で決めたTopic名
6. GitHub Actionsで `Airリザーブ空き監視` を手動実行してテスト

## 注意

Airリザーブ側の画面構造が変更されると、日付や空き時間の検出部分の修正が必要になる可能性があります。

また、GitHub Actionsのcronは「10分ちょうど」に必ず実行される保証はなく、数分程度ずれることがあります。

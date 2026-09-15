# 取得済み生データ（2026-09-15 時点）

| ファイル | 内容 |
|---|---|
| `Oj91UVdRjzw.info.json` | 橋本環奈の息分子（2026-08-04） メタデータ |
| `AE6JGXXEBQU.info.json` | ヴォイニッチ手稿（2026-08-10） メタデータ |
| `60rpcKkB7d0.info.json` | ピラミッド（2026-09-11） メタデータ |
| `comments_AE6JGXXEBQU.json` | ヴォイニッチ回 コメント150件（高評価順） |

取得方法: `yt-dlp --extractor-args "youtube:player_client=android_vr"`
（通常のwebクライアントはデータセンターIPからは429/bot判定でブロックされる）

字幕(json3)はサイズが大きいためコミットしていない。再取得コマンド:
```
yt-dlp --skip-download --extractor-args "youtube:player_client=android_vr" \
  --write-auto-subs --write-subs --sub-langs "ja.*,en.*" --sub-format json3 \
  -o "%(id)s" "https://www.youtube.com/watch?v=<ID>"
```

<!-- D1 스키마 변경을 어떻게 추가/적용하는지 안내. -->

# D1 마이그레이션

새 마이그레이션은 `NNNN_<short_name>.sql` 형식으로 추가한다.

## 로컬 적용
```
wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --local
```

## prod 적용
PR 머지 후 수동으로:
```
wrangler d1 migrations apply popory-portal --config infra/wrangler/api.toml --remote
```

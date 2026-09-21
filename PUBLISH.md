# Публикация в GitHub (bezuglyy/car_techlan)

```bash
# из папки этого пакета (D:\Car_Techlan\12-GitHub\car_techlan)
git init
git add .
git commit -m "feat: Car Techlan HA integration v1.1.0 (события, управление сервером, сенсоры)"
git branch -M main
git remote add origin https://github.com/bezuglyy/car_techlan.git   # создайте пустой репозиторий на GitHub
git push -u origin main
git tag v1.1.0 && git push origin v1.1.0
```

После публикации интеграция ставится через HACS как custom repository (категория Integration).
При выпуске новой версии: поднять `version` в `custom_components/car_techlan/manifest.json`, коммит, тег (например `v1.2.0`).

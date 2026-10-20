# T-34 — стенд СУБД: PostgreSQL в Docker и проверки на MS SQL

Стенд для разработки раздела «СУБД» и разведки перед спекой. Рабочие серверы заказчика
для разработки не используются. MS SQL у заказчика есть; PostgreSQL поднимается локально
в Docker.

**Команды ниже не прогнаны.** На 13.10.2026 Docker Desktop на машине разработки
не был запущен (`docker version` не достучался до демона). После первого прогона
поправить этот абзац и отметить, что сработало.

## PostgreSQL в Docker

Нужен запущенный Docker Desktop в режиме Linux-контейнеров. Команды — для PowerShell.

**1. Контейнер.** Версия образа зафиксирована: у `postgres:18` другой каталог данных,
и команда тома для него не подходит. Порт 5433 — на случай, если 5432 занят.

```powershell
docker run -d --name onecstarter-pg `
  -e POSTGRES_PASSWORD=<пароль postgres> `
  -p 5433:5432 `
  -v onecstarter-pgdata:/var/lib/postgresql/data `
  postgres:17

docker exec onecstarter-pg pg_isready -U postgres
```

Пароль выберите сами и в репозиторий не записывайте. Изнутри контейнера `psql` и `pgbench`
входят без пароля (локальный сокет); пароль нужен для подключения снаружи, с хоста.

**2. Тестовые базы и роль с минимальными правами.** SQL подаётся через стандартный ввод:
Windows PowerShell 5.1 портит кавычки внутри аргументов внешних программ.

```powershell
@'
CREATE DATABASE test_ib1;
CREATE DATABASE test_ib2;
CREATE DATABASE "Test_IB_Mixed";
CREATE ROLE sizer LOGIN PASSWORD '<пароль sizer>';
REVOKE CONNECT ON DATABASE test_ib2 FROM PUBLIC;
'@ | docker exec -i onecstarter-pg psql -U postgres -v ON_ERROR_STOP=1

docker exec onecstarter-pg pgbench -U postgres -i -s 10 test_ib1
```

Зачем каждая:

| База | Что проверяет |
| --- | --- |
| `test_ib1` | заполнена `pgbench` (масштаб 10), заметный размер |
| `test_ib2` | пустая; у `PUBLIC` отнято право `CONNECT` — что увидит роль без прав |
| `Test_IB_Mixed` | имя в смешанном регистре: в PostgreSQL имя в кавычках регистрозависимо, а «имя базы на сервере СУБД» по умолчанию берётся из `Ref` |

**3. Проверки — это разведка T-34, результаты записать сюда же.**

От суперпользователя:

```powershell
@'
SELECT datname, pg_database_size(datname) AS bytes, pg_size_pretty(pg_database_size(datname))
FROM pg_database WHERE NOT datistemplate ORDER BY datname;
SELECT count(*) AS wal_files, pg_size_pretty(sum(size)) AS wal_size FROM pg_ls_waldir();
'@ | docker exec -i onecstarter-pg psql -U postgres
```

Ожидание, которое надо подтвердить или опровергнуть: у `pg_ls_waldir()` нет столбца
с базой — журнал предзаписи общий на кластер, а значит разбивки «данные + журнал» для
отдельной базы PostgreSQL не существует (**[?]**, сверить и с документацией PostgreSQL).

От роли `sizer` — по TCP с проверкой пароля, а не через локальный сокет, то есть так же,
как будет подключаться программа (спросит пароль):

```powershell
docker exec -it onecstarter-pg psql "host=localhost user=sizer dbname=postgres" `
  -c "SELECT pg_database_size('test_ib1');"
docker exec -it onecstarter-pg psql "host=localhost user=sizer dbname=postgres" `
  -c "SELECT pg_database_size('test_ib2');"
docker exec -it onecstarter-pg psql "host=localhost user=sizer dbname=postgres" `
  -c "SELECT pg_database_size('test_ib_mixed');"
```

Ожидания (**[?]**): первая — число; вторая — отказ в доступе (нет `CONNECT`); третья —
«база не существует», потому что настоящее имя `Test_IB_Mixed`. Если так и выйдет,
то сравнение имён в T-34 должно быть точным, а сообщение пользователю — понятным
(«база не найдена на инстансе», а не текст ошибки драйвера).

**4. Убрать стенд.**

```powershell
docker stop onecstarter-pg
docker rm onecstarter-pg
docker volume rm onecstarter-pgdata
```

## MS SQL — проверки на имеющемся сервере

Только чтение. Если сервер не тестовый, создание логина из пункта 2 не выполнять.

**1. Размеры файлов по базам и по типу файла.** От учётной записи с полными правами:

```sql
SELECT DB_NAME(database_id) AS db, type_desc, COUNT(*) AS files,
       SUM(CAST(size AS bigint)) * 8 / 1024 AS size_mb
FROM sys.master_files
GROUP BY database_id, type_desc
ORDER BY db, type_desc;

SELECT SERVERPROPERTY('ProductVersion') AS version,
       SERVERPROPERTY('InstanceName') AS instance;
```

`size` — в страницах по 8 КБ. `type_desc` разделяет `ROWS` (данные) и `LOG` (журнал);
у одной базы файлов каждого типа может быть несколько.

**2. Что видит логин без прав** (только на тестовом сервере):

```sql
CREATE LOGIN sizer WITH PASSWORD = '<пароль sizer>';
-- войти как sizer и выполнить запрос из п. 1
GRANT VIEW ANY DEFINITION TO sizer;
-- повторить запрос из п. 1
DROP LOGIN sizer;
```

Записать: сколько строк видно до `GRANT` и после. Это определит, какие права программа
будет просить у администратора СУБД (**[?]**).

**3. Какие ODBC-драйверы стоят на машине.** От этого зависит выбор драйвера в T-34:

```powershell
Get-OdbcDriver | Where-Object Name -like "*SQL*" | Select-Object Name, Platform
```

## Результаты

_Заполнить после прогона: дата, что сработало, ответы на ожидания с пометкой [?]._

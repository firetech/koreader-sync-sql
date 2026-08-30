# Koreader position sync server

## Description

This is a simple implementation of the KOReader (https://github.com/koreader/koreader) position sync server for self-hosting at home which has docker support for arm and amd64 :) _This is a fork of https://github.com/b1n4ryj4n/koreader-sync rewritten to use an SQL backend instead of TinyDB._

## Dependencies

* FastAPI : https://github.com/tiangolo/fastapi
* SQLAlchemy: https://www.sqlalchemy.org/
* Uvicorn: https://www.uvicorn.org/
* Python-dotenv: https://saurabh-kumar.com/python-dotenv/

## Install and run

```bash
pip install -r requirements.txt

uvicorn kosync:app --host 0.0.0.0 --port 8081

```

## SQLite migration from TinyDB

This version stores its data in SQLite using SQLAlchemy. If you already have a TinyDB database from an older deployment, migrate it with the dedicated script:

```bash
python migrate_from_tinydb.py [path/to/db.json] [sqlite:///path/to/sqlite.db]
```

To preview the migration without writing any new data:

```bash
python migrate_from_tinydb.py --dry-run [path/to/db.json] [sqlite:///path/to/sqlite.db]
```

To use this tool, you may need to run `pip install tinydb` first, it's not included in requirements.txt.

## Or via Docker

To build locally:

```bash
docker build --rm=true --tag=kosync:latest .
docker compose up -d
```

## Environment Variables

* DATABASE_URL

Set this to a SQLite database URL if you want to override the default location. Example:

```bash
DATABASE_URL=sqlite:///data/kosync.db
```

* RECEIVE_RANDOM_DEVICE_ID ("True"|"False")

Set it true to retrieve always a random device id to force a progress sync. 
This is usefull if you only sync your progress from one device and 
usually delete the *.sdr files with some cleaning tools.

* OPEN_REGISTRATIONS ("True"|"False")

Enable/disable new registrations to the server. Useful if you want to run a private server for a few users, although it doesn't necessarily improve security by itself.
Set to True (enabled) by default.

## Connection

* Use http://IP:8081 as custom sync server
* Recommendation: Setup a reverse proxy for example with Nginx Proxy Manager (https://nginxproxymanager.com/) to connect with https

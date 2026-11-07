"""Print the Home Assistant credentials from a Mi Fitness pairing database.

Usage:
    python extract_credentials.py path/to/eco_local_device_db

The database lives on a ROOTED phone at
    /data/data/com.mi.health/databases/eco_local_device_db
(pull it with `su -c cp` + `adb pull`).  It contains your rope's pairing
credentials: treat the output like a password and never publish it.
"""
import sqlite3
import sys


def main(path: str) -> None:
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT name, model, app_device_id, token FROM eco_local_device"
    ).fetchall()
    if not rows:
        sys.exit("no paired eco devices found in this database")
    for name, model, app_device_id, token in rows:
        print(f"device : {name} ({model})")
        print(f"app_device_id: {app_device_id}")
        print(f"token        : {token}")
        print()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])

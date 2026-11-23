"""SQLite cache of per-file analysis so rescans and resumed scans are fast."""

import json
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    size INTEGER, mtime INTEGER,
    w INTEGER, h INTEGER, fmt TEXT,
    phash INTEGER, sha TEXT,
    emb BLOB, emb_model TEXT,
    error TEXT
)
"""

PAIR_SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    pa TEXT, pb TEXT, stamp TEXT, res TEXT,
    PRIMARY KEY (pa, pb)
)
"""

# Groups the user kept entirely ("not duplicates"); hidden from later scans.
# A group comes back if any member file changes or a new file joins it.
IGNORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS ignored (
    gid INTEGER, path TEXT, size INTEGER, mtime INTEGER
)
"""

COLS = "path, size, mtime, w, h, fmt, phash, sha, emb, emb_model, error, tiny"


class Cache:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.path = path
        try:
            self._open()
        except sqlite3.DatabaseError:
            # Corrupt cache: start over rather than fail the scan.
            for suffix in ("", "-wal", "-shm"):
                try:
                    os.remove(path + suffix)
                except OSError:
                    pass
            self._open()

    def _open(self):
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.execute(SCHEMA)
        self.db.execute(PAIR_SCHEMA)
        self.db.execute(IGNORE_SCHEMA)
        self.db.execute("CREATE INDEX IF NOT EXISTS ignored_path ON ignored(path)")
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(files)")}
        if "tiny" not in cols:  # upgrade older caches
            self.db.execute("ALTER TABLE files ADD COLUMN tiny BLOB")
        self.db.execute("SELECT count(*) FROM files LIMIT 1").fetchone()
        self.db.commit()

    def lookup(self, paths):
        out = {}
        for s in range(0, len(paths), 500):
            chunk = paths[s:s + 500]
            q = f"SELECT {COLS} FROM files WHERE path IN ({','.join('?' * len(chunk))})"
            for row in self.db.execute(q, chunk):
                out[row[0]] = row
        return out

    def upsert(self, rows):
        if rows:
            self.db.executemany(
                f"INSERT OR REPLACE INTO files ({COLS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            self.db.commit()

    def set_sha(self, pairs):
        if pairs:
            self.db.executemany("UPDATE files SET sha=? WHERE path=?", pairs)
            self.db.commit()

    # ----- keypoint verification results; stamp = sizes+mtimes of both files -----
    def get_pairs(self, items):
        """items: [(pa, pb, stamp)] -> {(pa, pb): result dict} for valid entries."""
        out = {}
        for s in range(0, len(items), 400):
            chunk = items[s:s + 400]
            q = ("SELECT pa, pb, stamp, res FROM pairs WHERE "
                 + " OR ".join(["(pa=? AND pb=?)"] * len(chunk)))
            args = [x for pa, pb, _ in chunk for x in (pa, pb)]
            want = {(pa, pb): st for pa, pb, st in chunk}
            for pa, pb, st, res in self.db.execute(q, args):
                if want.get((pa, pb)) == st:
                    out[(pa, pb)] = json.loads(res)
        return out

    def put_pairs(self, rows):
        """rows: [(pa, pb, stamp, result dict)]"""
        if rows:
            self.db.executemany("INSERT OR REPLACE INTO pairs VALUES (?,?,?,?)",
                                [(a, b, s, json.dumps(r)) for a, b, s, r in rows])
            self.db.commit()

    # ----- hidden ("not duplicates") groups -----
    def add_ignored(self, groups):
        """groups: [[(path, size, mtime), ...], ...] -> their new group ids"""
        gid = (self.db.execute("SELECT COALESCE(MAX(gid), 0) FROM ignored").fetchone()[0] or 0)
        rows, gids = [], []
        for g in groups:
            gid += 1
            gids.append(gid)
            rows += [(gid, p, int(s), int(m)) for p, s, m in g]
        self.db.executemany("INSERT INTO ignored VALUES (?,?,?,?)", rows)
        self.db.commit()
        return gids

    def remove_ignored(self, gids):
        """Show these hidden groups again (forget that they were kept)."""
        if gids:
            self.db.executemany("DELETE FROM ignored WHERE gid=?", [(int(g),) for g in gids])
            self.db.commit()

    def ignored_index(self):
        """{(path, size, mtime): gid}"""
        return {(p, s, m): g for g, p, s, m in self.db.execute("SELECT gid, path, size, mtime FROM ignored")}

    def count_ignored(self):
        return self.db.execute("SELECT COUNT(DISTINCT gid) FROM ignored").fetchone()[0]

    def clear_ignored(self):
        self.db.execute("DELETE FROM ignored")
        self.db.commit()

    def forget(self, paths):
        if paths:
            self.db.executemany("DELETE FROM files WHERE path=?", [(p,) for p in paths])
            self.db.commit()

    def clear(self):
        self.db.execute("DELETE FROM files")
        self.db.execute("DELETE FROM pairs")
        self.db.execute("DELETE FROM ignored")    # hidden groups show again after a cache reset
        self.db.commit()
        self.db.execute("VACUUM")

    def close(self):
        try:
            self.db.close()
        except Exception:
            pass

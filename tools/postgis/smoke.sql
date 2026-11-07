.bail on
SELECT sqlite_version();
SELECT sqlite_compileoption_used('ENABLE_FTS5') AND sqlite_compileoption_used('ENABLE_SESSION') AND sqlite_compileoption_used('ENABLE_RTREE');
CREATE VIRTUAL TABLE search USING fts5(body);
INSERT INTO search(search,rank) VALUES('secure-delete',1);
INSERT INTO search(rowid,body) VALUES(-9223372036854775808,'one record'),(9223372036854775807,'two record');
INSERT INTO search(search) VALUES('optimize');
DELETE FROM search WHERE rowid=-9223372036854775808;
SELECT count(*) FROM search WHERE search MATCH 'record';
PRAGMA integrity_check;

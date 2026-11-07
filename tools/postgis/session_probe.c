#include <stdio.h>
#include <stdlib.h>
#include "sqlite3.h"
#define OK(x) do { int rc=(x); if(rc!=SQLITE_OK){fprintf(stderr,"rc=%d at line %d\n",rc,__LINE__);exit(1);} } while(0)
static int reject_conflict(void *ctx,int kind,sqlite3_changeset_iter *it){(void)ctx;(void)kind;(void)it;return SQLITE_CHANGESET_ABORT;}
int main(void){
 sqlite3 *a=0,*b=0;sqlite3_session *s=0;void *changes=0;int n=0;sqlite3_stmt *q=0;
 OK(sqlite3_open(":memory:",&a));OK(sqlite3_open(":memory:",&b));
 OK(sqlite3_exec(a,"CREATE TABLE items(id INTEGER PRIMARY KEY, text TEXT);",0,0,0));
 OK(sqlite3_exec(b,"CREATE TABLE items(id INTEGER PRIMARY KEY, text TEXT);",0,0,0));
 OK(sqlite3session_create(a,"main",&s));OK(sqlite3session_attach(s,"items"));
 OK(sqlite3_exec(a,"INSERT INTO items VALUES(1,'synthetic original'),(2,'Unicode café');UPDATE items SET text='updated' WHERE id=1;",0,0,0));
 OK(sqlite3session_changeset(s,&n,&changes));if(n<=0)return 2;
 OK(sqlite3changeset_apply(b,n,changes,0,reject_conflict,0));
 OK(sqlite3_prepare_v2(b,"SELECT count(*) FROM items WHERE (id=1 AND text='updated') OR (id=2 AND text='Unicode café')",-1,&q,0));
 if(sqlite3_step(q)!=SQLITE_ROW || sqlite3_column_int(q,0)!=2)return 3;
 sqlite3_finalize(q);sqlite3_free(changes);sqlite3session_delete(s);sqlite3_close(a);sqlite3_close(b);
 printf("SESSION_ROUNDTRIP_OK %s %s\n",sqlite3_libversion(),sqlite3_sourceid());return 0;
}

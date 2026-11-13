use std::time::Instant;
const N_BULK: u64 = 100_000;
const N_SINGLE: u64 = 3_000;
const BATCH: u64 = 100;
fn payload() -> Vec<u8> { vec![7u8; 200] }
fn key(i: u64) -> [u8; 8] { i.to_be_bytes() }
fn report(db: &str, what: &str, n: u64, t: Instant) {
    let s = t.elapsed().as_secs_f64();
    println!("{db:12} {what:34} n={n:7} {s:8.3}s {:10.0} ops/s", n as f64 / s);
}

fn sqlite(sync: &str, path: &str) {
    use rusqlite::Connection;
    let _ = std::fs::remove_file(path);
    let _ = std::fs::remove_file(format!("{path}-wal"));
    let _ = std::fs::remove_file(format!("{path}-shm"));
    let mut c = Connection::open(path).unwrap();
    c.pragma_update(None, "journal_mode", "WAL").unwrap();
    c.pragma_update(None, "synchronous", sync).unwrap();
    c.execute_batch("CREATE TABLE tasks(id INTEGER PRIMARY KEY, state INTEGER NOT NULL, payload BLOB NOT NULL);
                     CREATE INDEX t_state ON tasks(state,id);").unwrap();
    let name = format!("sqlite-{sync}");
    let p = payload();
    let t = Instant::now();
    for b in 0..(N_BULK / 1000) {
        let tx = c.transaction().unwrap();
        { let mut st = tx.prepare_cached("INSERT INTO tasks(id,state,payload) VALUES(?,0,?)").unwrap();
          for i in 0..1000 { st.execute(rusqlite::params![(b*1000+i) as i64, &p]).unwrap(); } }
        tx.commit().unwrap();
    }
    report(&name, "enqueue, 1000 per commit", N_BULK, t);
    // single claim+ack, one commit each
    let t = Instant::now();
    for _ in 0..N_SINGLE {
        let tx = c.transaction().unwrap();
        let id: i64 = tx.query_row("SELECT id FROM tasks WHERE state=0 ORDER BY id LIMIT 1", [], |r| r.get(0)).unwrap();
        tx.execute("UPDATE tasks SET state=1 WHERE id=?", [id]).unwrap();
        tx.commit().unwrap();
        let tx = c.transaction().unwrap();
        tx.execute("DELETE FROM tasks WHERE id=?", [id]).unwrap();
        tx.commit().unwrap();
    }
    report(&name, "claim(1 commit)+ack(1 commit) /task", N_SINGLE, t);
    // batched claim, batched ack
    let t = Instant::now();
    let mut done = 0u64;
    while done < N_SINGLE * 10 {
        let tx = c.transaction().unwrap();
        let ids: Vec<i64> = { let mut st = tx.prepare_cached("SELECT id FROM tasks WHERE state=0 ORDER BY id LIMIT ?").unwrap();
            st.query_map([BATCH as i64], |r| r.get(0)).unwrap().map(|x| x.unwrap()).collect() };
        for id in &ids { tx.execute("UPDATE tasks SET state=1 WHERE id=?", [id]).unwrap(); }
        tx.commit().unwrap();
        let tx = c.transaction().unwrap();
        for id in &ids { tx.execute("DELETE FROM tasks WHERE id=?", [id]).unwrap(); }
        tx.commit().unwrap();
        done += ids.len() as u64;
    }
    report(&name, "claim+ack, 100 per commit", done, t);
}

fn redb_run(path: &str) {
    use redb::{Database, TableDefinition, ReadableTable, Durability};
    const P: TableDefinition<u64, &[u8]> = TableDefinition::new("pending");
    const L: TableDefinition<u64, &[u8]> = TableDefinition::new("leased");
    let _ = std::fs::remove_file(path);
    let db = Database::create(path).unwrap();
    let p = payload();
    let t = Instant::now();
    for b in 0..(N_BULK / 1000) {
        let tx = db.begin_write().unwrap();
        { let mut t = tx.open_table(P).unwrap(); for i in 0..1000 { t.insert(b*1000+i, p.as_slice()).unwrap(); } }
        tx.commit().unwrap();
    }
    report("redb", "enqueue, 1000 per commit", N_BULK, t);
    let t = Instant::now();
    for _ in 0..N_SINGLE {
        let tx = db.begin_write().unwrap();
        let id = { let mut pt = tx.open_table(P).unwrap(); let mut lt = tx.open_table(L).unwrap();
            let (k, v) = pt.pop_first().unwrap().unwrap(); let id = k.value(); lt.insert(id, v.value()).unwrap(); id };
        tx.commit().unwrap();
        let tx = db.begin_write().unwrap();
        { let mut lt = tx.open_table(L).unwrap(); lt.remove(id).unwrap(); }
        tx.commit().unwrap();
    }
    report("redb", "claim(1 commit)+ack(1 commit) /task", N_SINGLE, t);
    let t = Instant::now();
    let mut done = 0u64;
    while done < N_SINGLE * 10 {
        let tx = db.begin_write().unwrap();
        let mut ids = vec![];
        { let mut pt = tx.open_table(P).unwrap(); let mut lt = tx.open_table(L).unwrap();
          for _ in 0..BATCH { let (k, v) = pt.pop_first().unwrap().unwrap(); let id = k.value(); lt.insert(id, v.value()).unwrap(); ids.push(id);} }
        tx.commit().unwrap();
        let tx = db.begin_write().unwrap();
        { let mut lt = tx.open_table(L).unwrap(); for id in &ids { lt.remove(*id).unwrap(); } }
        tx.commit().unwrap();
        done += ids.len() as u64;
    }
    report("redb", "claim+ack, 100 per commit", done, t);
    // non-durable commits (Durability::None) for contrast
    let mut tx = db.begin_write().unwrap(); tx.set_durability(Durability::None);
    drop(tx);
}

fn fjall_run(path: &str) {
    use fjall::{Config, PartitionCreateOptions, PersistMode};
    let _ = std::fs::remove_dir_all(path);
    let ks = Config::new(path).open().unwrap();
    let pend = ks.open_partition("pending", PartitionCreateOptions::default()).unwrap();
    let lea = ks.open_partition("leased", PartitionCreateOptions::default()).unwrap();
    let p = payload();
    let t = Instant::now();
    for b in 0..(N_BULK / 1000) {
        let mut batch = ks.batch();
        for i in 0..1000 { batch.insert(&pend, key(b*1000+i), &p); }
        batch.commit().unwrap();
        ks.persist(PersistMode::SyncAll).unwrap();
    }
    report("fjall", "enqueue, 1000 per commit", N_BULK, t);
    let t = Instant::now();
    for _ in 0..N_SINGLE {
        let (k, v) = pend.first_key_value().unwrap().unwrap();
        let mut batch = ks.batch(); batch.remove(&pend, k.clone()); batch.insert(&lea, k.clone(), v); batch.commit().unwrap();
        ks.persist(PersistMode::SyncAll).unwrap();
        let mut batch = ks.batch(); batch.remove(&lea, k); batch.commit().unwrap();
        ks.persist(PersistMode::SyncAll).unwrap();
    }
    report("fjall", "claim(1 commit)+ack(1 commit) /task", N_SINGLE, t);
    let t = Instant::now();
    let mut done = 0u64;
    while done < N_SINGLE * 10 {
        let mut batch = ks.batch(); let mut ks_ids = vec![];
        for _ in 0..BATCH { let (k, v) = pend.first_key_value().unwrap().unwrap(); batch.remove(&pend, k.clone()); batch.insert(&lea, k.clone(), v); ks_ids.push(k); }
        batch.commit().unwrap(); ks.persist(PersistMode::SyncAll).unwrap();
        let mut batch = ks.batch(); for k in &ks_ids { batch.remove(&lea, k.clone()); }
        batch.commit().unwrap(); ks.persist(PersistMode::SyncAll).unwrap();
        done += ks_ids.len() as u64;
    }
    report("fjall", "claim+ack, 100 per commit", done, t);
}

fn main() {
    let dir = std::env::args().nth(1).unwrap_or("/tmp/qb".into());
    std::fs::create_dir_all(&dir).unwrap();
    sqlite("FULL", &format!("{dir}/s_full.db"));
    sqlite("NORMAL", &format!("{dir}/s_norm.db"));
    redb_run(&format!("{dir}/r.redb"));
    fjall_run(&format!("{dir}/fj"));
}

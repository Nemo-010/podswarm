use std::sync::Arc;
use tokio::net::TcpStream;
use tokio_rustls::TlsConnector;
use futures_util_shim::*;
mod futures_util_shim { pub use tokio_tungstenite::tungstenite::Message; }
#[tokio::main(flavor = "current_thread")]
async fn main() {
    let c = rusqlite::Connection::open_in_memory().unwrap();
    c.execute_batch("PRAGMA journal_mode=WAL; CREATE TABLE t(a)").unwrap();
    let v: serde_json::Value = serde_json::from_str("{\"a\":1}").unwrap();
    let mut roots = rustls::RootCertStore::empty();
    roots.extend(webpki_roots::TLS_SERVER_ROOTS.iter().cloned());
    let cfg = rustls::ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider())).with_safe_default_protocol_versions().unwrap().with_root_certificates(roots).with_no_client_auth();
    let conn = TlsConnector::from(Arc::new(cfg));
    if std::env::args().count() > 5 {
        let s = TcpStream::connect("example.com:443").await.unwrap();
        let t = conn.connect("example.com".try_into().unwrap(), s).await.unwrap();
        let (mut ws, _) = tokio_tungstenite::client_async("wss://example.com/", t).await.unwrap();
        let _ = &mut ws;
        let _ = Message::Text("x".into());
    }
    println!("{v} sqlite ok");
}

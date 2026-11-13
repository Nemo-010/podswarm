// Connection scale probe: TLS 1.3 (rustls, ring) + WebSocket (tungstenite) over loopback.
// server mode: accepts, answers each text "hb" with "hback", reports RSS and CPU.
// client mode: opens N connections, sends "hb" every interval, reports connect time.
use futures_util::{SinkExt, StreamExt};
use std::sync::{Arc, atomic::{AtomicU64, Ordering}};
use std::time::{Duration, Instant};
use tokio::net::{TcpListener, TcpStream};
use tokio_rustls::{TlsAcceptor, TlsConnector};
use tokio_tungstenite::tungstenite::Message;

fn status(k: &str) -> f64 {
    let s = std::fs::read_to_string("/proc/self/status").unwrap();
    for l in s.lines() { if let Some(r) = l.strip_prefix(k) { return r.trim().trim_end_matches(" kB").trim().parse().unwrap(); } }
    0.0
}
fn proc_cpu() -> f64 {
    let mut ru: libc::rusage = unsafe { std::mem::zeroed() };
    unsafe { libc::getrusage(libc::RUSAGE_SELF, &mut ru) };
    ru.ru_utime.tv_sec as f64 + ru.ru_utime.tv_usec as f64 / 1e6 + ru.ru_stime.tv_sec as f64 + ru.ru_stime.tv_usec as f64 / 1e6
}
#[derive(Debug)]
struct NoVerify;
impl rustls::client::danger::ServerCertVerifier for NoVerify {
    fn verify_server_cert(&self, _: &rustls::pki_types::CertificateDer<'_>, _: &[rustls::pki_types::CertificateDer<'_>], _: &rustls::pki_types::ServerName<'_>, _: &[u8], _: rustls::pki_types::UnixTime) -> Result<rustls::client::danger::ServerCertVerified, rustls::Error> { Ok(rustls::client::danger::ServerCertVerified::assertion()) }
    fn verify_tls12_signature(&self, _: &[u8], _: &rustls::pki_types::CertificateDer<'_>, _: &rustls::DigitallySignedStruct) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> { Ok(rustls::client::danger::HandshakeSignatureValid::assertion()) }
    fn verify_tls13_signature(&self, _: &[u8], _: &rustls::pki_types::CertificateDer<'_>, _: &rustls::DigitallySignedStruct) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> { Ok(rustls::client::danger::HandshakeSignatureValid::assertion()) }
    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> { rustls::crypto::ring::default_provider().signature_verification_algorithms.supported_schemes() }
}

fn main() {
    let a: Vec<String> = std::env::args().collect();
    let mode = a[1].clone();
    let get = |k: &str, d: &str| a.iter().position(|x| x == k).map(|i| a[i + 1].clone()).unwrap_or(d.into());
    let threads: usize = get("--threads", "4").parse().unwrap();
    let port: u16 = get("--port", "34443").parse().unwrap();
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(threads).enable_all().build().unwrap();
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    if mode == "server" {
        let ck = rcgen::generate_simple_self_signed(vec!["localhost".into()]).unwrap();
        let cert = ck.cert.der().clone();
        let key = rustls::pki_types::PrivateKeyDer::try_from(ck.signing_key.serialize_der()).unwrap();
        let cfg = rustls::ServerConfig::builder_with_provider(provider).with_safe_default_protocol_versions().unwrap().with_no_client_auth().with_single_cert(vec![cert], key).unwrap();
        let acc = TlsAcceptor::from(Arc::new(cfg)); let rbuf: usize = get("--rbuf", "0").parse().unwrap();
        let conns = Arc::new(AtomicU64::new(0));
        let msgs = Arc::new(AtomicU64::new(0));
        rt.block_on(async move {
            let l = TcpListener::bind(("127.0.0.1", port)).await.unwrap();
            let (c2, m2) = (conns.clone(), msgs.clone());
            tokio::spawn(async move {
                let mut last = (Instant::now(), proc_cpu(), 0u64);
                loop {
                    tokio::time::sleep(Duration::from_secs(2)).await;
                    let (now, cpu, m) = (Instant::now(), proc_cpu(), m2.load(Ordering::Relaxed));
                    println!("SERVER conns={} rss_mib={:.1} fds={} cpu_cores_last={:.3} msgs_per_s={:.0}", c2.load(Ordering::Relaxed), status("VmRSS:") / 1024.0, std::fs::read_dir("/proc/self/fd").unwrap().count(), (cpu - last.1) / now.duration_since(last.0).as_secs_f64(), (m - last.2) as f64 / now.duration_since(last.0).as_secs_f64());
                    last = (now, cpu, m);
                }
            });
            loop {
                let (s, _) = l.accept().await.unwrap();
                let (acc, conns, msgs) = (acc.clone(), conns.clone(), msgs.clone()); let rbuf = rbuf;
                tokio::spawn(async move {
                    let Ok(t) = acc.accept(s).await else { return };
                    let Ok(mut ws) = tokio_tungstenite::accept_async_with_config(t, if rbuf > 0 { Some(tokio_tungstenite::tungstenite::protocol::WebSocketConfig::default().read_buffer_size(rbuf).write_buffer_size(0)) } else { None }).await else { return };
                    conns.fetch_add(1, Ordering::Relaxed);
                    while let Some(Ok(m)) = ws.next().await {
                        if let Message::Text(_) = m { msgs.fetch_add(1, Ordering::Relaxed); if ws.send(Message::Text("hback".into())).await.is_err() { break; } }
                    }
                    conns.fetch_sub(1, Ordering::Relaxed);
                });
            }
        });
    } else {
        let n: usize = get("--n", "1000").parse().unwrap();
        let hb_ms: u64 = get("--hb-ms", "10000").parse().unwrap();
        let secs: u64 = get("--secs", "20").parse().unwrap();
        let conc: usize = get("--conc", "100000").parse().unwrap();
        let cfg = rustls::ClientConfig::builder_with_provider(provider).with_safe_default_protocol_versions().unwrap().dangerous().with_custom_certificate_verifier(Arc::new(NoVerify)).with_no_client_auth();
        let conn = TlsConnector::from(Arc::new(cfg));
        rt.block_on(async move {
            let sem = Arc::new(tokio::sync::Semaphore::new(conc));
            let t0 = Instant::now();
            let ok = Arc::new(AtomicU64::new(0));
            let lat = Arc::new(std::sync::Mutex::new(Vec::<u32>::new()));
            let mut hs = vec![];
            for i in 0..n {
                let (conn, sem, ok, lat) = (conn.clone(), sem.clone(), ok.clone(), lat.clone());
                hs.push(tokio::spawn(async move {
                    let p = sem.acquire().await.unwrap();
                    let t = Instant::now();
                    let s = match TcpStream::connect(("127.0.0.1", port)).await { Ok(s) => s, Err(_) => return };
                    let Ok(tls) = conn.connect("localhost".try_into().unwrap(), s).await else { return };
                    let Ok((mut ws, _)) = tokio_tungstenite::client_async("ws://localhost/", tls).await else { return };
                    lat.lock().unwrap().push(t.elapsed().as_micros() as u32);
                    ok.fetch_add(1, Ordering::Relaxed);
                    drop(p);
                    let mut k = i as u64 * 7919;
                    tokio::time::sleep(Duration::from_millis(k % hb_ms.max(1))).await;
                    loop {
                        if ws.send(Message::Text("hb".into())).await.is_err() { return; }
                        if ws.next().await.is_none() { return; }
                        k += 1;
                        tokio::time::sleep(Duration::from_millis(hb_ms)).await;
                    }
                }));
            }
            // wait for all connected
            while ok.load(Ordering::Relaxed) < n as u64 && t0.elapsed() < Duration::from_secs(300) { tokio::time::sleep(Duration::from_millis(50)).await; }
            let storm = t0.elapsed().as_secs_f64();
            let mut l = lat.lock().unwrap().clone(); l.sort_unstable();
            let p = |q: f64| l.get(((l.len() as f64 * q) as usize).min(l.len().saturating_sub(1))).copied().unwrap_or(0) as f64 / 1e3;
            println!("CLIENT connected={} of {n} in {storm:.2}s  handshake_ms p50={:.0} p99={:.0}  client_rss_mib={:.0}", ok.load(Ordering::Relaxed), p(0.5), p(0.99), status("VmRSS:") / 1024.0);
            tokio::time::sleep(Duration::from_secs(secs)).await;
        });
        std::process::exit(0);
    }
}

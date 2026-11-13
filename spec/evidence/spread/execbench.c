// Measures the cost of exec interception rungs: fork+execve+wait of a
// program, bare, under seccomp user notification (CONTINUE), under
// notification with the sync wake-up flag, and under ptrace with a
// seccomp RET_TRACE filter on execve only. Also a syscall loop under
// each rung, to show the cost on the calls that are not exec.
#define _GNU_SOURCE
#include <errno.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <linux/audit.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <poll.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#ifndef SECCOMP_IOCTL_NOTIF_SET_FLAGS
#define SECCOMP_IOCTL_NOTIF_SET_FLAGS SECCOMP_IOW(4, __u64)
#endif
#ifndef SECCOMP_USER_NOTIF_FD_SYNC_WAKE_UP
#define SECCOMP_USER_NOTIF_FD_SYNC_WAKE_UP (1UL << 0)
#endif

static const char *prog = "/bin/true";
static int iters = 2000;

static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

// The workload: N times fork, exec prog, wait. Then 1e6 getppid calls.
static void workload(int out) {
  char *argv[] = {(char *)prog, NULL};
  char *envp[] = {NULL};
  double t0 = now();
  for (int i = 0; i < iters; i++) {
    pid_t p = fork();
    if (p == 0) {
      execve(prog, argv, envp);
      _exit(127);
    }
    int st;
    waitpid(p, &st, 0);
    if (!WIFEXITED(st) || WEXITSTATUS(st) != 0) { fprintf(stderr, "bad status %x\n", st); _exit(3); }
  }
  double t1 = now();
  for (int i = 0; i < 1000000; i++) syscall(SYS_getppid);
  double t2 = now();
  double r[2] = {(t1 - t0) / iters, (t2 - t1) / 1e6 * 1000.0};
  if (write(out, r, sizeof r) != sizeof r) _exit(4);
  _exit(0);
}

static int install(uint32_t action, unsigned flags) {
  struct sock_filter f[] = {
      BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
      BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execve, 2, 0),
      BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execveat, 1, 0),
      BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
      BPF_STMT(BPF_RET | BPF_K, action),
  };
  struct sock_fprog fp = {.len = 5, .filter = f};
  prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
  return syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, flags, &fp);
}

static void report(const char *name, int rd) {
  double r[2];
  if (read(rd, r, sizeof r) != sizeof r) { printf("%-14s failed\n", name); return; }
  printf("%-14s exec+wait %8.1f us   getppid %6.1f ns\n", name, r[0], r[1]);
}

static void run_bare(void) {
  int pp[2]; pipe(pp);
  pid_t w = fork();
  if (w == 0) workload(pp[1]);
  waitpid(w, NULL, 0);
  report("bare", pp[0]);
}

static void run_notify(int sync) {
  int pp[2]; pipe(pp);
  pid_t s = fork();
  if (s == 0) {
    int lfd = install(SECCOMP_RET_USER_NOTIF, SECCOMP_FILTER_FLAG_NEW_LISTENER);
    if (lfd < 0) { perror("seccomp"); _exit(1); }
    if (sync && ioctl(lfd, SECCOMP_IOCTL_NOTIF_SET_FLAGS, SECCOMP_USER_NOTIF_FD_SYNC_WAKE_UP) < 0)
      perror("sync flag");
    pid_t w = fork();
    if (w == 0) { close(lfd); workload(pp[1]); }
    struct seccomp_notif_sizes sz;
    syscall(SYS_seccomp, SECCOMP_GET_NOTIF_SIZES, 0, &sz);
    struct seccomp_notif *req = calloc(1, sz.seccomp_notif);
    struct seccomp_notif_resp *resp = calloc(1, sz.seccomp_notif_resp);
    for (;;) {
      struct pollfd pf = {.fd = lfd, .events = POLLIN};
      int st0;
      if (poll(&pf, 1, 50) == 0) { if (waitpid(w, &st0, WNOHANG) == w) break; continue; }
      memset(req, 0, sz.seccomp_notif);
      if (ioctl(lfd, SECCOMP_IOCTL_NOTIF_RECV, req) < 0) {
        if (errno == EINTR) continue;
        break;
      }
      memset(resp, 0, sz.seccomp_notif_resp);
      resp->id = req->id;
      resp->flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
      ioctl(lfd, SECCOMP_IOCTL_NOTIF_SEND, resp);
    }
    _exit(0);
  }
  waitpid(s, NULL, 0);
  report(sync ? "notify+sync" : "notify", pp[0]);
}

static void run_trace(void) {
  int pp[2]; pipe(pp);
  pid_t w = fork();
  if (w == 0) {
    ptrace(PTRACE_TRACEME, 0, 0, 0);
    raise(SIGSTOP);
    if (install(SECCOMP_RET_TRACE, 0) < 0) { perror("seccomp"); _exit(1); }
    workload(pp[1]);
  }
  int st;
  waitpid(w, &st, 0);
  ptrace(PTRACE_SETOPTIONS, w, 0,
         PTRACE_O_TRACESECCOMP | PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK |
             PTRACE_O_TRACECLONE | PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL);
  ptrace(PTRACE_CONT, w, 0, 0);
  for (;;) {
    pid_t p = waitpid(-1, &st, __WALL);
    if (p < 0) break;
    if (WIFEXITED(st) || WIFSIGNALED(st)) {
      if (p == w) break;
      continue;
    }
    int sig = 0;
    if (WIFSTOPPED(st)) {
      int s = WSTOPSIG(st);
      if (s != SIGTRAP && s != SIGSTOP) sig = s;
      if (s == SIGSTOP) sig = 0;
    }
    ptrace(PTRACE_CONT, p, 0, sig);
  }
  report("ptrace-exec", pp[0]);
}

static void run_trace_all(void) {
  int pp[2]; pipe(pp);
  pid_t w = fork();
  if (w == 0) {
    ptrace(PTRACE_TRACEME, 0, 0, 0);
    raise(SIGSTOP);
    workload(pp[1]);
  }
  int st;
  waitpid(w, &st, 0);
  ptrace(PTRACE_SETOPTIONS, w, 0,
         PTRACE_O_TRACESYSGOOD | PTRACE_O_TRACEFORK | PTRACE_O_TRACEVFORK |
             PTRACE_O_TRACECLONE | PTRACE_O_TRACEEXEC | PTRACE_O_EXITKILL);
  ptrace(PTRACE_SYSCALL, w, 0, 0);
  for (;;) {
    pid_t p = waitpid(-1, &st, __WALL);
    if (p < 0) break;
    if (WIFEXITED(st) || WIFSIGNALED(st)) {
      if (p == w) break;
      continue;
    }
    int sig = 0;
    if (WIFSTOPPED(st)) {
      int s = WSTOPSIG(st);
      if (s != SIGTRAP && s != (SIGTRAP | 0x80) && s != SIGSTOP) sig = s;
    }
    ptrace(PTRACE_SYSCALL, p, 0, sig);
  }
  report("ptrace-all", pp[0]);
}

int main(int argc, char **argv) {
  if (argc > 1) prog = argv[1];
  if (argc > 2) iters = atoi(argv[2]);
  run_bare();
  run_notify(0);
  run_notify(1);
  run_trace();
  run_trace_all();
  run_bare();
  return 0;
}

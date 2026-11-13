// Prototype of the "exec takeover" for x86_64: a seccomp user notification
// supervisor that, for a chosen program, seizes the calling thread, lets
// the real execve run, stops the new image at PTRACE_EVENT_EXEC before its
// first instruction, and injects an execve of a stub with the final argv.
// The stub here is /bin/sh printing the argv it took over. The workload
// tests fork+execve, posix_spawn (CLONE_VM|CLONE_VFORK) and a failed exec.
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/filter.h>
#include <linux/seccomp.h>
#include <poll.h>
#include <spawn.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/prctl.h>
#include <sys/ptrace.h>
#include <sys/syscall.h>
#include <sys/user.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

extern char **environ;
static double now(void) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  return t.tv_sec * 1e6 + t.tv_nsec / 1e3;
}

static int memw(pid_t p, uint64_t addr, const void *buf, size_t n) {
  char path[64];
  snprintf(path, sizeof path, "/proc/%d/mem", p);
  int fd = open(path, O_RDWR);
  if (fd < 0) return -1;
  ssize_t r = pwrite(fd, buf, n, (off_t)addr);
  close(fd);
  return r == (ssize_t)n ? 0 : -1;
}

static int memr(pid_t p, uint64_t addr, void *buf, size_t n) {
  char path[64];
  snprintf(path, sizeof path, "/proc/%d/mem", p);
  int fd = open(path, O_RDONLY);
  if (fd < 0) return -1;
  ssize_t r = pread(fd, buf, n, (off_t)addr);
  close(fd);
  return r == (ssize_t)n ? 0 : -1;
}

// Inject execve("/bin/sh", ["sh","-c",SCRIPT,"stub", <orig argv...>], envp)
static int takeover(pid_t tid, int st0) {
  int st = st0;
  pid_t w = tid;
  if (w <= 0 || !WIFSTOPPED(st) || (st >> 8) != (SIGTRAP | (PTRACE_EVENT_EXEC << 8))) {
    fprintf(stderr, "takeover: no exec stop (st=%x)\n", st);
    return -1;
  }
  struct user_regs_struct r;
  ptrace(PTRACE_GETREGS, tid, 0, &r);
  fprintf(stderr, "exec stop: rip %llx rsp %llx\n", r.rip, r.rsp);
  uint64_t sp = r.rsp;
  uint64_t argc;
  memr(tid, sp, &argc, 8);
  uint64_t oargv[64];
  if (argc > 60) argc = 60;
  memr(tid, sp + 8, oargv, 8 * argc);
  uint64_t envp = sp + 8 * (argc + 2);
  // Scratch area well below the initial stack pointer.
  uint64_t base = (sp - 8192) & ~15ULL, cur = base;
  const char *strs[] = {"/bin/sh", "sh", "-c", "echo \"stub pid $$ took over: $*\"", "stub"};
  uint64_t ptrs[5];
  for (int i = 0; i < 5; i++) {
    size_t n = strlen(strs[i]) + 1;
    memw(tid, cur, strs[i], n);
    ptrs[i] = cur;
    cur += (n + 15) & ~15ULL;
  }
  uint64_t argv[70];
  int k = 0;
  argv[k++] = ptrs[1];
  argv[k++] = ptrs[2];
  argv[k++] = ptrs[3];
  argv[k++] = ptrs[4];
  for (uint64_t i = 0; i < argc; i++) argv[k++] = oargv[i];
  argv[k++] = 0;
  uint64_t argv_addr = cur;
  memw(tid, argv_addr, argv, 8 * k);
  // Trampoline at rip: mov eax,59 ; syscall
  unsigned char tramp[] = {0xb8, 0x3b, 0, 0, 0, 0x0f, 0x05};
  memw(tid, r.rip, tramp, sizeof tramp);
  r.rdi = ptrs[0];
  r.rsi = argv_addr;
  r.rdx = envp;
  r.r10 = 0x5057534d;
  ptrace(PTRACE_SETREGS, tid, 0, &r);
  int wr = memw(tid, r.rip, tramp, sizeof tramp);
  fprintf(stderr, "tramp write %d\n", wr);
  ptrace(PTRACE_CONT, tid, 0, 0);
  w = waitpid(tid, &st, __WALL);
  fprintf(stderr, "after inject: w %d st %x\n", w, st);
  if (w < 0 || (st >> 8) != (SIGTRAP | (PTRACE_EVENT_EXEC << 8))) {
    fprintf(stderr, "takeover: injected exec failed (st=%x)\n", st);
    return -1;
  }
  ptrace(PTRACE_DETACH, tid, 0, 0);
  return 0;
}

static int install(void) {
  struct sock_filter f[] = {
      BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, nr)),
      BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execve, 3, 0),
      BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, SYS_execveat, 2, 0),
      BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
      BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
      // execve with the cookie in the 4th argument register passes.
      BPF_STMT(BPF_LD | BPF_W | BPF_ABS, offsetof(struct seccomp_data, args[3])),
      BPF_JUMP(BPF_JMP | BPF_JEQ | BPF_K, 0x5057534d, 0, 1),
      BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_ALLOW),
      BPF_STMT(BPF_RET | BPF_K, SECCOMP_RET_USER_NOTIF),
  };
  struct sock_fprog fp = {.len = 9, .filter = f};
  prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0);
  return syscall(SYS_seccomp, SECCOMP_SET_MODE_FILTER, SECCOMP_FILTER_FLAG_NEW_LISTENER, &fp);
}

static void workload(void) {
  setvbuf(stdout, NULL, _IONBF, 0);
  // 1. fork + execve of a moved program
  pid_t p = fork();
  if (p == 0) {
    char *a[] = {"/bin/echo", "real echo ran (WRONG)", NULL};
    execve("/bin/echo", a, environ);
    _exit(127);
  }
  int st;
  waitpid(p, &st, 0);
  printf("fork+execve: child %d status %d\n", p, WEXITSTATUS(st));
  // 2. posix_spawn (CLONE_VM|CLONE_VFORK in glibc) of a moved program
  char *a2[] = {"echo", "spawned", "args", NULL};
  posix_spawnp(&p, "echo", NULL, NULL, a2, environ);
  waitpid(p, &st, 0);
  printf("posix_spawnp: child %d status %d\n", p, WEXITSTATUS(st));
  // 3. a local program, not moved
  p = fork();
  if (p == 0) {
    char *a[] = {"/bin/true", NULL};
    execve("/bin/true", a, environ);
    _exit(127);
  }
  waitpid(p, &st, 0);
  printf("local /bin/true: status %d\n", WEXITSTATUS(st));
  // 4. a failed exec keeps the kernel's own errno
  p = fork();
  if (p == 0) {
    char *a[] = {"/nonexistent/echo", NULL};
    execve("/nonexistent/echo", a, environ);
    _exit(errno == ENOENT ? 42 : 43);
  }
  waitpid(p, &st, 0);
  printf("failed exec: status %d (42 = ENOENT seen by caller)\n", WEXITSTATUS(st));
  // 5. timing: 200 moved execs
  double t0 = now();
  for (int i = 0; i < 200; i++) {
    p = fork();
    if (p == 0) {
      int fd = open("/dev/null", O_WRONLY);
      dup2(fd, 1);
      char *a[] = {"/bin/echo", "x", NULL};
      execve("/bin/echo", a, environ);
      _exit(127);
    }
    waitpid(p, &st, 0);
  }
  double t1 = now();
  for (int i = 0; i < 200; i++) {
    p = fork();
    if (p == 0) {
      int fd = open("/dev/null", O_WRONLY);
      dup2(fd, 1);
      char *a[] = {"/bin/sh", "-c", "echo \"stub pid $$ took over: $*\"", "stub", "/bin/echo", "x", NULL};
      execve("/bin/sh", a, environ);
      _exit(127);
    }
    waitpid(p, &st, 0);
  }
  double t2 = now();
  printf("moved exec via takeover %.0f us; direct exec of the stub %.0f us\n", (t1 - t0) / 200, (t2 - t1) / 200);
  _exit(0);
}

int main(void) {
  int lfd = install();
  if (lfd < 0) { perror("seccomp"); return 1; }
  pid_t w = fork();
  if (w == 0) { close(lfd); workload(); }
  struct seccomp_notif_sizes sz;
  syscall(SYS_seccomp, SECCOMP_GET_NOTIF_SIZES, 0, &sz);
  struct seccomp_notif *req = calloc(1, sz.seccomp_notif);
  struct seccomp_notif_resp *resp = calloc(1, sz.seccomp_notif_resp);
  pid_t armed = 0;
  int quiet = 0;
  for (;;) {
    int st0;
    if (armed) {
      pid_t r = waitpid(armed, &st0, __WALL | WNOHANG);
      if (r == armed) {
        if (WIFEXITED(st0) || WIFSIGNALED(st0)) { if (!quiet) fprintf(stderr, "armed %d exited %d\n", armed, WEXITSTATUS(st0)); armed = 0; }
        else { int rc = takeover(armed, st0); if (!quiet) fprintf(stderr, "takeover %d rc %d\n", armed, rc); armed = 0; }
      }
    }
    struct pollfd pf = {.fd = lfd, .events = POLLIN};
    if (poll(&pf, 1, armed ? 0 : 50) == 0) { if (!armed && waitpid(w, &st0, WNOHANG) == w) break; continue; }
    memset(req, 0, sz.seccomp_notif);
    if (ioctl(lfd, SECCOMP_IOCTL_NOTIF_RECV, req) < 0) continue;
    char path[256] = {0};
    memr(req->pid, req->data.args[0], path, sizeof path - 1);
    const char *b = strrchr(path, '/');
    b = b ? b + 1 : path;
    int move = strcmp(b, "echo") == 0;
    if (!quiet) fprintf(stderr, "notif pid %d path %s move %d%s\n", req->pid, path, move, req->pid == armed ? " (retry of armed)" : "");
    if (strcmp(path, "/bin/sh") == 0) quiet = 1;
    if (move && req->pid != armed) {
      if (ptrace(PTRACE_SEIZE, req->pid, 0, PTRACE_O_TRACEEXEC) < 0) { perror("seize"); move = 0; }
      else armed = req->pid;
    }
    memset(resp, 0, sz.seccomp_notif_resp);
    resp->id = req->id;
    resp->flags = SECCOMP_USER_NOTIF_FLAG_CONTINUE;
    ioctl(lfd, SECCOMP_IOCTL_NOTIF_SEND, resp);
  }
  return 0;
}

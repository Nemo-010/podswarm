#include <unistd.h>
int main(int c, char **v) { (void)c; v[0] = "/bin/true"; execv("/bin/true", v); return 127; }

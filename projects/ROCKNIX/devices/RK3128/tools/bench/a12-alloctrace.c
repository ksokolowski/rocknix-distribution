// SPDX-License-Identifier: GPL-2.0-or-later
// LD_PRELOAD: sum malloc/calloc/realloc bytes per call site; print the top sites at exit.
#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
extern void *__libc_malloc(size_t);
extern void *__libc_calloc(size_t, size_t);
extern void *__libc_realloc(void *, size_t);
#define N 8192
static struct { void *site; size_t bytes, count; const char *file; unsigned long off; } t[N];
static void note(void *site, size_t n)
{
	size_t h = ((uintptr_t)site >> 2) % N;
	for (int i = 0; i < N; i++, h = (h + 1) % N) {
		if (!t[h].site || t[h].site == site) {
			if (!t[h].site) {
				Dl_info d = { 0 };
				t[h].site = site;
				if (dladdr(site, &d) && d.dli_fname) {
					t[h].file = d.dli_fname;
					t[h].off = (unsigned long)((char *)site - (char *)d.dli_fbase);
				}
			}
			t[h].bytes += n; t[h].count++;
			return;
		}
	}
}
void *malloc(size_t n) { note(__builtin_return_address(0), n); return __libc_malloc(n); }
void *calloc(size_t a, size_t b) { note(__builtin_return_address(0), a * b); return __libc_calloc(a, b); }
void *realloc(void *p, size_t n) { note(__builtin_return_address(0), n); return __libc_realloc(p, n); }
static int cmp(const void *a, const void *b)
{
	size_t x = *(const size_t *)((const char *)a + sizeof(void *)), y = *(const size_t *)((const char *)b + sizeof(void *));
	return x < y ? 1 : x > y ? -1 : 0;
}
__attribute__((destructor)) static void dump(void)
{
	size_t total = 0;
	qsort(t, N, sizeof t[0], cmp);
	for (int i = 0; i < N; i++) total += t[i].bytes;
	fprintf(stderr, "alloctrace total %zu KiB\n", total >> 10);
	for (int i = 0; i < 40 && t[i].site; i++) {
		fprintf(stderr, "alloctrace %8zu KiB %7zu x %s+0x%lx\n", t[i].bytes >> 10, t[i].count,
			t[i].file ? t[i].file : "?", t[i].off);
	}
}

/* SPDX-License-Identifier: MIT */
/* Compile Mesa's actual tiler; do not copy or replace its implementation. */
#ifndef _GNU_SOURCE
#define _GNU_SOURCE
#endif
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include "pan_tiling.c"

/* Keep runtime format dispatch, as in the profiled Mesa function. */
__attribute__((noinline)) static void
access_image(void *tiled, void *linear, unsigned x, unsigned y,
             unsigned w, unsigned h, unsigned tiled_stride,
             unsigned linear_stride, const struct util_format_description *desc,
             enum pan_interleave_zs interleave, bool store, bool aligned)
{
   if (aligned)
      pan_access_tiled_image_generic_aligned(tiled, linear, x, y, w, h,
                                            tiled_stride, linear_stride,
                                            desc, interleave, store);
   else
      pan_access_tiled_image_generic(tiled, linear, x, y, w, h,
                                    tiled_stride, linear_stride,
                                    desc, interleave, store);
}

static void *
allocate(size_t size)
{
   void *p = NULL;
   if (posix_memalign(&p, 64, size)) {
      fprintf(stderr, "allocation failed\n");
      exit(1);
   }
   return p;
}

/* Independent oracle: calculate each bit of the documented U-interleave. */
static size_t
tiled_offset(unsigned x, unsigned y, unsigned stride, unsigned bytes)
{
   unsigned index = 0;
   for (unsigned bit = 0; bit < 4; ++bit) {
      unsigned xb = (x >> bit) & 1, yb = (y >> bit) & 1;
      index |= (xb ^ yb) << (2 * bit);
      index |= yb << (2 * bit + 1);
   }
   return (y / 16) * stride + ((x / 16) * 256 + index) * bytes;
}

static void
check(unsigned bytes, unsigned x, unsigned y, unsigned w, unsigned h,
      enum pan_interleave_zs interleave, bool aligned)
{
   const unsigned stride = 128 * 16 * bytes;
   const unsigned src_bytes = interleave == PAN_INTERLEAVE_STENCIL ? 1 : bytes;
   const unsigned linear_stride = (w + 16) * src_bytes;
   const size_t tiled_size = stride * 8, linear_size = linear_stride * h;
   const size_t guard = 64;
   uint8_t *tile = allocate(tiled_size + 2 * guard);
   uint8_t *expected = allocate(tiled_size + 2 * guard);
   uint8_t *linear = allocate(linear_size + 2 * guard);
   uint8_t *loaded = allocate(linear_size + 2 * guard);
   uint8_t *expected_load = allocate(linear_size + 2 * guard);
   struct util_format_description desc = {
      .block = {.bits = bytes * 8, .width = 1, .height = 1, .depth = 1},
   };
   memset(tile, 0xa5, tiled_size + 2 * guard);
   memset(linear, 0x5a, linear_size + 2 * guard);
   memset(loaded, 0x3c, linear_size + 2 * guard);
   for (size_t i = 0; i < linear_size; ++i)
      linear[guard + i] = (uint8_t)(i * 37 + (i >> 8) * 13);
   memcpy(expected, tile, tiled_size + 2 * guard);
   memcpy(expected_load, loaded, linear_size + 2 * guard);
   for (unsigned row = 0; row < h; ++row) {
      for (unsigned col = 0; col < w; ++col) {
         size_t t = guard + tiled_offset(x + col, y + row, stride, bytes);
         size_t s = guard + row * linear_stride + col * src_bytes;
         unsigned count = interleave == PAN_INTERLEAVE_DEPTH ? 3 : src_bytes;
         unsigned offset = interleave == PAN_INTERLEAVE_STENCIL ? 3 : 0;
         memcpy(expected + t + offset, linear + s, count);
         memcpy(expected_load + s, linear + s, count);
         if (interleave == PAN_INTERLEAVE_DEPTH)
            expected_load[s + 3] = 0;
      }
   }
   access_image(tile + guard, linear + guard, x, y, w, h, stride,
                linear_stride, &desc, interleave, true, aligned);
   if (memcmp(tile, expected, tiled_size + 2 * guard)) {
      fprintf(stderr, "store mismatch: bpp=%u x=%u y=%u w=%u h=%u aspect=%d aligned=%d\n",
              bytes * 8, x, y, w, h, interleave, aligned);
      exit(1);
   }
   access_image(tile + guard, loaded + guard, x, y, w, h, stride,
                linear_stride, &desc, interleave, false, aligned);
   if (memcmp(loaded, expected_load, linear_size + 2 * guard)) {
      fprintf(stderr, "load mismatch: bpp=%u x=%u y=%u w=%u h=%u aspect=%d aligned=%d\n",
              bytes * 8, x, y, w, h, interleave, aligned);
      exit(1);
   }
   free(expected_load);
   free(loaded);
   free(linear);
   free(expected);
   free(tile);
}

static double
seconds(void)
{
   struct timespec ts;
   if (clock_gettime(CLOCK_MONOTONIC, &ts)) {
      perror("clock_gettime");
      exit(1);
   }
   return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static void
benchmark(unsigned bytes, unsigned w, unsigned h, unsigned iterations)
{
   unsigned tile_stride = w * 16 * bytes, linear_stride = w * bytes;
   size_t size = (size_t)w * h * bytes;
   uint8_t *tile = allocate(size), *linear = allocate(size);
   struct util_format_description desc = {
      .block = {.bits = bytes * 8, .width = 1, .height = 1, .depth = 1},
   };
   memset(tile, 0, size);
   memset(linear, 0x5a, size);
   for (unsigned store = 0; store < 2; ++store) {
      for (unsigned warm = 0; warm < 8; ++warm)
         access_image(tile, linear, 0, 0, w, h, tile_stride, linear_stride,
                      &desc, PAN_INTERLEAVE_NONE, store, true);
      for (unsigned repeat = 0; repeat < 3; ++repeat) {
         double start = seconds();
         for (unsigned i = 0; i < iterations; ++i)
            access_image(tile, linear, 0, 0, w, h, tile_stride, linear_stride,
                         &desc, PAN_INTERLEAVE_NONE, store, true);
         double elapsed = seconds() - start;
         printf("{\"operation\":\"%s\",\"bpp\":%u,\"width\":%u,\"height\":%u,"
                "\"repeat\":%u,\"iterations\":%u,\"ms_per_image\":%.6f,"
                "\"payload_mib_per_second\":%.3f}\n",
                store ? "store" : "load", bytes * 8, w, h, repeat,
                iterations, elapsed * 1000 / iterations,
                (double)size * iterations / elapsed / (1024 * 1024));
         fflush(stdout);
      }
   }
   free(linear);
   free(tile);
}

int
main(int argc, char **argv)
{
   unsigned iterations = 0;
   if (argc == 2) {
      char *end;
      errno = 0;
      unsigned long value = strtoul(argv[1], &end, 10);
      if (errno || !*argv[1] || *end || !value || value > 10000) {
         fprintf(stderr, "iterations must be between 1 and 10000\n");
         return 2;
      }
      iterations = value;
   } else if (argc != 1) {
      fprintf(stderr, "usage: %s [iterations]\n", argv[0]);
      return 2;
   }
   unsigned cases = 0;
   const unsigned sizes[] = {1, 2, 3, 4, 6, 8, 12, 16};
   const unsigned offsets[] = {0, 1, 15, 16, 31};
   const unsigned widths[] = {1, 15, 16, 17, 33};
   for (unsigned b = 0; b < ARRAY_SIZE(sizes); ++b) {
      for (unsigned x = 0; x < ARRAY_SIZE(offsets); ++x) {
         for (unsigned y = 0; y < ARRAY_SIZE(offsets); ++y) {
            for (unsigned w = 0; w < ARRAY_SIZE(widths); ++w) {
               check(sizes[b], offsets[x], offsets[y], widths[w], 19,
                     PAN_INTERLEAVE_NONE, false);
               ++cases;
            }
         }
      }
      if (util_is_power_of_two_nonzero(sizes[b])) {
         check(sizes[b], 16, 16, 48, 32, PAN_INTERLEAVE_NONE, true);
         ++cases;
      }
   }
   for (unsigned aspect = PAN_INTERLEAVE_DEPTH; aspect <= PAN_INTERLEAVE_STENCIL; ++aspect) {
      check(4, 16, 16, 48, 32, aspect, true);
      check(4, 15, 1, 33, 19, aspect, false);
      cases += 2;
   }
   printf("{\"correctness_cases\":%u,\"status\":\"pass\"}\n", cases);
   if (iterations) {
      for (unsigned bytes = 2; bytes <= 4; bytes += 2) {
         benchmark(bytes, 384, 224, iterations);
         benchmark(bytes, 512, 256, iterations);
         benchmark(bytes, 1024, 592, iterations);
      }
   }
   return 0;
}
